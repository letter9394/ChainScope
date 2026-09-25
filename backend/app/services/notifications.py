from __future__ import annotations

import asyncio
import html
import smtplib
from email.message import EmailMessage
from typing import Awaitable, Callable

import httpx
from sqlalchemy import select

from app.config import Settings
from app.database import (
    Database, EmailVerificationRow, NotificationDeliveryRow,
    NotificationPreferenceRow, UserRow,
)
from app.models import AlertEvent, NotificationSettingsResponse, NotificationSettingsUpdate


SMTP_PROVIDERS = {
    "smtp.qq.com": "QQ 邮箱",
    "smtp.163.com": "网易 163 邮箱",
    "smtp.126.com": "网易 126 邮箱",
    "smtp.yeah.net": "网易 Yeah 邮箱",
}


def brevo_is_configured(settings: Settings) -> bool:
    return bool(settings.brevo_api_key and settings.brevo_sender_email)


def smtp_is_configured(settings: Settings) -> bool:
    return bool(
        settings.smtp_host
        and settings.smtp_from_email
        and settings.smtp_username
        and settings.smtp_password
    )


def email_is_configured(settings: Settings) -> bool:
    return brevo_is_configured(settings) or smtp_is_configured(settings)


def email_provider(settings: Settings) -> str:
    if brevo_is_configured(settings):
        return "Brevo HTTPS API"
    if not settings.smtp_host:
        return "尚未配置"
    return SMTP_PROVIDERS.get(settings.smtp_host.lower(), "自定义 SMTP")


def configured_sender(settings: Settings) -> str | None:
    if brevo_is_configured(settings):
        return settings.brevo_sender_email
    return settings.smtp_from_email


def masked_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    visible = local[:2] if len(local) > 1 else local[:1]
    return f"{visible}***@{domain}"


class NotificationRepository:
    def __init__(self, database: Database, user_id: int) -> None:
        self.database = database
        self.user_id = user_id

    def get_or_create(self) -> NotificationPreferenceRow:
        with self.database.session() as session:
            row = session.get(NotificationPreferenceRow, self.user_id)
            if row is None:
                row = NotificationPreferenceRow(
                    user_id=self.user_id,
                    legacy_telegram_enabled=False,
                    legacy_telegram_chat_id=None,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return row

    def update(self, payload: NotificationSettingsUpdate) -> NotificationPreferenceRow:
        with self.database.session() as session:
            row = session.get(NotificationPreferenceRow, self.user_id)
            if row is None:
                row = NotificationPreferenceRow(
                    user_id=self.user_id,
                    legacy_telegram_enabled=False,
                    legacy_telegram_chat_id=None,
                )
                session.add(row)
            row.email_enabled = payload.email_enabled
            row.legacy_telegram_enabled = False
            row.legacy_telegram_chat_id = None
            session.commit()
            session.refresh(row)
            return row


def preference_response(row: NotificationPreferenceRow, settings: Settings) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        email_enabled=row.email_enabled,
        email_available=email_is_configured(settings),
        email_provider=email_provider(settings),
        email_sender=masked_email(configured_sender(settings)),
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
            verification = session.get(EmailVerificationRow, user_id)
        if preference is None or user is None or not preference.email_enabled:
            return
        if verification is not None and verification.verified_at is None:
            return

        for event in events:
            await self._attempt(event, user_id, lambda: self._send_alert_email(user.email, event))

    async def _attempt(
        self,
        event: AlertEvent,
        user_id: int,
        sender: Callable[[], Awaitable[None]],
    ) -> None:
        with self.database.session() as session:
            existing = session.scalar(
                select(NotificationDeliveryRow).where(
                    NotificationDeliveryRow.event_id == event.id,
                    NotificationDeliveryRow.channel == "email",
                )
            )
        if existing is not None and existing.status == "sent":
            return

        status = "failed"
        error_message = None
        for delay in (0, 1, 3):
            if delay:
                await asyncio.sleep(delay)
            try:
                await sender()
                status = "sent"
                error_message = None
                break
            except Exception as exc:  # Email failures must never stop the alert scheduler.
                error_message = str(exc)[:1000]

        with self.database.session() as session:
            row = session.scalar(
                select(NotificationDeliveryRow).where(
                    NotificationDeliveryRow.event_id == event.id,
                    NotificationDeliveryRow.channel == "email",
                )
            )
            if row is None:
                row = NotificationDeliveryRow(
                    event_id=event.id,
                    user_id=user_id,
                    channel="email",
                    status=status,
                    error_message=error_message,
                )
                session.add(row)
            else:
                row.status = status
                row.error_message = error_message
            session.commit()

    async def send_test_email(self, recipient: str) -> None:
        self._require_configuration()
        message = self._base_message(
            recipient=recipient,
            subject="[ChainScope] 邮箱通知测试成功",
            plain=(
                "这是一封 ChainScope 测试邮件。\n\n"
                "如果你收到它，说明 SMTP 配置、发件邮箱和收件邮箱已经连通。"
                f"\n\n打开 ChainScope：{self.settings.public_app_url}/#account"
            ),
            html_body=(
                "<h2 style='margin:0 0 16px;color:#153c32'>ChainScope 邮箱通知测试成功</h2>"
                "<p>如果你收到这封邮件，说明 SMTP 配置、发件邮箱和收件邮箱已经连通。</p>"
                "<p>之后当风险规则从安全状态首次越过阈值时，系统会自动发送邮件。</p>"
                f"<p><a href='{html.escape(self.settings.public_app_url)}/#account'>打开 ChainScope</a></p>"
                "<p style='color:#667b74;font-size:12px'>本邮件仅用于测试通知，不构成投资建议。</p>"
            ),
        )
        await asyncio.to_thread(self._send_message_sync, message)

    async def send_password_reset_email(self, recipient: str, reset_url: str) -> None:
        self._require_configuration()
        safe_url = html.escape(reset_url, quote=True)
        message = self._base_message(
            recipient=recipient,
            subject="[ChainScope] 重置登录密码",
            plain=(
                "你正在重置 ChainScope 登录密码。\n\n"
                f"请在 30 分钟内打开以下链接：\n{reset_url}\n\n"
                "如果不是你本人操作，请忽略这封邮件，原密码不会改变。"
            ),
            html_body=(
                "<h2 style='margin:0 0 16px;color:#153c32'>重置 ChainScope 登录密码</h2>"
                "<p>请在 30 分钟内点击下面的按钮设置新密码：</p>"
                "<p><a style='display:inline-block;padding:12px 20px;background:#36cfa5;"
                "color:#08251d;text-decoration:none;border-radius:24px;font-weight:700' "
                f"href='{safe_url}'>设置新密码</a></p>"
                "<p>如果不是你本人操作，请忽略这封邮件，原密码不会改变。</p>"
                "<p style='color:#667b74;font-size:12px'>链接使用一次后自动失效。</p>"
            ),
        )
        await asyncio.to_thread(self._send_message_sync, message)

    async def send_email_verification(self, recipient: str, verification_url: str) -> None:
        self._require_configuration()
        safe_url = html.escape(verification_url, quote=True)
        message = self._base_message(
            recipient=recipient,
            subject="[ChainScope] 验证你的邮箱",
            plain=(
                "欢迎注册 ChainScope。\n\n"
                f"请在 24 小时内打开以下链接完成邮箱验证：\n{verification_url}\n\n"
                "完成验证后即可开启邮件风险预警。如果不是你本人注册，请忽略本邮件。"
            ),
            html_body=(
                "<h2 style='margin:0 0 16px;color:#153c32'>验证你的 ChainScope 邮箱</h2>"
                "<p>点击下面的按钮完成验证，之后即可开启邮件风险预警：</p>"
                "<p><a style='display:inline-block;padding:12px 20px;background:#36cfa5;"
                "color:#08251d;text-decoration:none;border-radius:24px;font-weight:700' "
                f"href='{safe_url}'>验证邮箱</a></p>"
                "<p>链接在 24 小时后失效。如果不是你本人注册，请忽略本邮件。</p>"
                "<p style='color:#667b74;font-size:12px'>ChainScope 不会通过邮件索取密码或 API Key。</p>"
            ),
        )
        await asyncio.to_thread(self._send_message_sync, message)

    async def _send_alert_email(self, recipient: str, event: AlertEvent) -> None:
        self._require_configuration()
        message = self._base_message(
            recipient=recipient,
            subject=f"[ChainScope] {event.title}",
            plain=(
                f"{event.title}\n\n{event.message}\n\n"
                f"风险级别：{'高风险' if event.severity == 'critical' else '提醒'}\n"
                f"查看预警：{self.settings.public_app_url}/#alerts\n\n"
                "本邮件仅用于市场研究，不构成投资建议。"
            ),
            html_body=(
                f"<h2 style='margin:0 0 16px;color:#153c32'>{html.escape(event.title)}</h2>"
                f"<p style='font-size:16px'>{html.escape(event.message)}</p>"
                f"<p><strong>风险级别：</strong>{'高风险' if event.severity == 'critical' else '提醒'}</p>"
                f"<p><a href='{html.escape(self.settings.public_app_url)}/#alerts'>查看 ChainScope 预警中心</a></p>"
                "<p style='color:#667b74;font-size:12px'>本邮件仅用于市场研究，不构成投资建议。</p>"
            ),
        )
        await asyncio.to_thread(self._send_message_sync, message)

    def _base_message(self, recipient: str, subject: str, plain: str, html_body: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"ChainScope <{configured_sender(self.settings)}>"
        message["To"] = recipient
        message.set_content(plain)
        message.add_alternative(
            "<!doctype html><html><body style='font-family:Arial,sans-serif;line-height:1.7;"
            "max-width:640px;margin:24px auto;padding:24px;background:#f5faf8;color:#17352d'>"
            f"{html_body}</body></html>",
            subtype="html",
        )
        return message

    def _require_configuration(self) -> None:
        if self.settings.brevo_api_key or self.settings.brevo_sender_email:
            if not brevo_is_configured(self.settings):
                raise RuntimeError("Brevo API Key 和发件邮箱必须同时配置")
            return
        if not smtp_is_configured(self.settings):
            raise RuntimeError("邮件服务尚未完整配置")
        if self.settings.smtp_security.lower() not in {"ssl", "starttls", "plain"}:
            raise RuntimeError("SMTP_SECURITY 必须是 ssl、starttls 或 plain")

    def _send_message_sync(self, message: EmailMessage) -> None:
        self._require_configuration()
        if brevo_is_configured(self.settings):
            self._send_via_brevo(message)
            return
        security = self.settings.smtp_security.lower()
        smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        with smtp_class(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as client:
            client.ehlo()
            if security == "starttls":
                client.starttls()
                client.ehlo()
            client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(message)

    def _send_via_brevo(self, message: EmailMessage) -> None:
        plain_part = message.get_body(preferencelist=("plain",))
        html_part = message.get_body(preferencelist=("html",))
        payload = {
            "sender": {"name": "ChainScope", "email": self.settings.brevo_sender_email},
            "to": [{"email": str(message["To"])}],
            "subject": str(message["Subject"]),
            "textContent": plain_part.get_content() if plain_part else "",
            "htmlContent": html_part.get_content() if html_part else "",
        }
        response = httpx.post(
            self.settings.brevo_api_url,
            headers={
                "accept": "application/json",
                "api-key": self.settings.brevo_api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=self.settings.smtp_timeout_seconds,
        )
        if response.status_code >= 400:
            try:
                detail = str(response.json().get("message", "未知错误"))[:300]
            except (ValueError, AttributeError):
                detail = response.text[:300]
            raise RuntimeError(f"Brevo API 返回 {response.status_code}：{detail}")
