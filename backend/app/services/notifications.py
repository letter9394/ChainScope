from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy import select

from app.config import Settings
from app.database import (
    AlertEventRow,
    Database,
    NotificationDeliveryRow,
    NotificationPreferenceRow,
    UserRow,
)
from app.models import AlertEvent, NotificationSettingsResponse, NotificationSettingsUpdate


class NotificationRepository:
    def __init__(self, database: Database, user_id: int) -> None:
        self.database = database
        self.user_id = user_id

    def get_or_create(self) -> NotificationPreferenceRow:
        with self.database.session() as session:
            row = session.get(NotificationPreferenceRow, self.user_id)
            if row is None:
                row = NotificationPreferenceRow(user_id=self.user_id)
                session.add(row)
                session.commit()
                session.refresh(row)
            return row

    def update(self, payload: NotificationSettingsUpdate) -> NotificationPreferenceRow:
        with self.database.session() as session:
            row = session.get(NotificationPreferenceRow, self.user_id)
            if row is None:
                row = NotificationPreferenceRow(user_id=self.user_id)
                session.add(row)
            row.email_enabled = payload.email_enabled
            row.telegram_enabled = payload.telegram_enabled
            row.telegram_chat_id = payload.telegram_chat_id.strip() if payload.telegram_chat_id else None
            session.commit()
            session.refresh(row)
            return row


def preference_response(row: NotificationPreferenceRow, settings: Settings) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        email_enabled=row.email_enabled,
        telegram_enabled=row.telegram_enabled,
        telegram_chat_id=row.telegram_chat_id,
        email_available=bool(settings.smtp_host and settings.smtp_from_email),
        telegram_available=bool(settings.telegram_bot_token),
        schedule_seconds=settings.alert_check_seconds,
        schedule_mode="Web 服务在线时后台运行",
    )


class NotificationService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    async def deliver(self, user_id: int, events: list[AlertEvent]) -> None:
        if not events:
            return
        with self.database.session() as session:
            preference = session.get(NotificationPreferenceRow, user_id)
            user = session.get(UserRow, user_id)
        if preference is None or user is None:
            return

        for event in events:
            if preference.email_enabled:
                await self._attempt(event, user_id, "email", lambda: self._send_email(user.email, event))
            if preference.telegram_enabled and preference.telegram_chat_id:
                await self._attempt(
                    event,
                    user_id,
                    "telegram",
                    lambda: self._send_telegram(preference.telegram_chat_id or "", event),
                )

    async def _attempt(self, event: AlertEvent, user_id: int, channel: str, sender) -> None:
        with self.database.session() as session:
            existing = session.scalar(
                select(NotificationDeliveryRow).where(
                    NotificationDeliveryRow.event_id == event.id,
                    NotificationDeliveryRow.channel == channel,
                )
            )
        if existing is not None:
            return
        status = "sent"
        error_message = None
        try:
            await sender()
        except Exception as exc:  # Delivery failures must never stop the alert scheduler.
            status = "failed"
            error_message = str(exc)[:1000]
        with self.database.session() as session:
            session.add(
                NotificationDeliveryRow(
                    event_id=event.id,
                    user_id=user_id,
                    channel=channel,
                    status=status,
                    error_message=error_message,
                )
            )
            session.commit()

    async def _send_telegram(self, chat_id: str, event: AlertEvent) -> None:
        if not self.settings.telegram_bot_token:
            raise RuntimeError("Telegram Bot Token 尚未配置")
        text = f"⚠️ {event.title}\n{event.message}\n{self.settings.public_app_url}/#alerts"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()

    async def _send_email(self, recipient: str, event: AlertEvent) -> None:
        if not self.settings.smtp_host or not self.settings.smtp_from_email:
            raise RuntimeError("SMTP 邮件服务尚未配置")

        def send() -> None:
            message = EmailMessage()
            message["Subject"] = f"[ChainScope] {event.title}"
            message["From"] = self.settings.smtp_from_email
            message["To"] = recipient
            message.set_content(f"{event.message}\n\n查看预警：{self.settings.public_app_url}/#alerts")
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as client:
                if self.settings.smtp_use_tls:
                    client.starttls()
                if self.settings.smtp_username and self.settings.smtp_password:
                    client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)

        await asyncio.to_thread(send)
