from __future__ import annotations

import asyncio
import html
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Awaitable, Callable

import httpx
from sqlalchemy import select

from app.config import Settings
from app.database import (
    Database, EmailVerificationRow, NotificationDeliveryRow,
    NotificationPreferenceRow, RiskDriftDeliveryRow, RiskDriftEventRow, UserRow,
)
from app.models import (
    AlertEvent, DriftEmailDelivery, NotificationSettingsResponse,
    NotificationSettingsUpdate, RiskDriftEvent,
)


SMTP_PROVIDERS = {
    "smtp.qq.com": "QQ 邮箱",
    "smtp.163.com": "网易 163 邮箱",
    "smtp.126.com": "网易 126 邮箱",
    "smtp.yeah.net": "网易 Yeah 邮箱",
}

logger = logging.getLogger("chainscope.notifications")
SUBMITTED_DRIFT_STATUSES = {"sent", "delivered", "bounced", "deferred", "blocked"}


def normalize_brevo_message_id(value: str) -> str:
    normalized = value.strip().removeprefix("<").removesuffix(">").strip()
    if not normalized or len(normalized) > 255:
        raise ValueError("Invalid Brevo message ID")
    return normalized


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
            row.drift_email_enabled = payload.drift_email_enabled
            row.legacy_telegram_enabled = False
            row.legacy_telegram_chat_id = None
            session.commit()
            session.refresh(row)
            return row

    def list_drift_deliveries(self, *, limit: int = 10) -> list[DriftEmailDelivery]:
        with self.database.session() as session:
            rows = list(session.execute(
                select(RiskDriftDeliveryRow, RiskDriftEventRow)
                .join(RiskDriftEventRow, RiskDriftEventRow.id == RiskDriftDeliveryRow.event_id)
                .where(RiskDriftDeliveryRow.user_id == self.user_id)
                .order_by(RiskDriftDeliveryRow.attempted_at.desc(), RiskDriftDeliveryRow.id.desc())
                .limit(limit)
            ))
        return [
            DriftEmailDelivery(
                event_id=event.id,
                coin_id=event.coin_id,
                symbol=event.symbol,
                title=event.title,
                status=delivery.status,
                attempted_at=(
                    delivery.attempted_at if delivery.attempted_at.tzinfo is not None
                    else delivery.attempted_at.replace(tzinfo=UTC)
                ).isoformat(),
                provider_event_at=(
                    (delivery.provider_event_at if delivery.provider_event_at.tzinfo is not None
                     else delivery.provider_event_at.replace(tzinfo=UTC)).isoformat()
                    if delivery.provider_event_at is not None else None
                ),
            )
            for delivery, event in rows
        ]

    @staticmethod
    def record_brevo_event(
        database: Database, *, message_id: str, recipient: str, status: str, event_at: datetime,
    ) -> str:
        """Apply authenticated, chronological provider updates to one matching email."""

        normalized_id = normalize_brevo_message_id(message_id)
        with database.session() as session:
            row = session.execute(
                select(RiskDriftDeliveryRow, UserRow)
                .join(UserRow, UserRow.id == RiskDriftDeliveryRow.user_id)
                .where(RiskDriftDeliveryRow.provider_message_id == normalized_id)
            ).one_or_none()
            if row is None:
                return "ignored"
            delivery, user = row
            if user.email.casefold() != recipient.strip().casefold():
                return "ignored"
            if delivery.status not in SUBMITTED_DRIFT_STATUSES:
                return "ignored"
            previous_at = delivery.provider_event_at
            if previous_at is not None:
                previous_at = previous_at if previous_at.tzinfo is not None else previous_at.replace(tzinfo=UTC)
                if event_at <= previous_at:
                    return "ignored"
            delivery.status = status
            delivery.provider_event_at = event_at
            session.commit()
            return "updated"


def preference_response(row: NotificationPreferenceRow, settings: Settings) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        email_enabled=row.email_enabled,
        drift_email_enabled=row.drift_email_enabled,
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

    async def deliver_drift_events(self, events: list[RiskDriftEvent]) -> dict[str, int]:
        """Deliver warning transitions to explicitly opted-in, verified users.

        Delivery rows make the operation safe to repeat after restarts. A per-user,
        per-asset cooldown suppresses a second warning transition without hiding the
        audit trail.
        """

        warnings = [
            event for event in events
            if event.severity == "warning" and event.current_status == "deteriorating"
        ]
        summary = {"sent": 0, "failed": 0, "suppressed": 0, "deduplicated": 0}
        if not warnings:
            return summary

        with self.database.session() as session:
            recipients = list(session.execute(
                select(UserRow, NotificationPreferenceRow)
                .join(
                    NotificationPreferenceRow,
                    NotificationPreferenceRow.user_id == UserRow.id,
                )
                .where(NotificationPreferenceRow.drift_email_enabled.is_(True))
            ))
            verification_by_user = {
                row.user_id: row
                for row in session.scalars(select(EmailVerificationRow))
            }

        for user, _preference in recipients:
            verification = verification_by_user.get(user.id)
            if verification is not None and verification.verified_at is None:
                continue
            for event in warnings:
                status = await self._attempt_drift_email(user, event)
                if status in summary:
                    summary[status] += 1
        return summary

    async def retry_failed_drift_events(self) -> dict[str, int]:
        """Retry recent failures on later monitor cycles while consent remains active."""

        summary = {"sent": 0, "failed": 0, "suppressed": 0, "deduplicated": 0}
        if not email_is_configured(self.settings):
            return summary
        now = datetime.now(UTC)
        retry_before = now - timedelta(minutes=30)
        event_after = now - timedelta(hours=24)
        with self.database.session() as session:
            rows = list(session.execute(
                select(RiskDriftDeliveryRow, RiskDriftEventRow, UserRow)
                .join(RiskDriftEventRow, RiskDriftEventRow.id == RiskDriftDeliveryRow.event_id)
                .join(UserRow, UserRow.id == RiskDriftDeliveryRow.user_id)
                .join(NotificationPreferenceRow, NotificationPreferenceRow.user_id == UserRow.id)
                .where(
                    RiskDriftDeliveryRow.channel == "email",
                    RiskDriftDeliveryRow.status == "failed",
                    RiskDriftDeliveryRow.attempted_at <= retry_before,
                    RiskDriftEventRow.created_at >= event_after,
                    RiskDriftEventRow.severity == "warning",
                    RiskDriftEventRow.current_status == "deteriorating",
                    NotificationPreferenceRow.drift_email_enabled.is_(True),
                )
                .order_by(RiskDriftDeliveryRow.attempted_at.asc())
                .limit(20)
            ))
            latest_event_by_coin = {
                event_row.coin_id: session.scalar(
                    select(RiskDriftEventRow.id)
                    .where(RiskDriftEventRow.coin_id == event_row.coin_id)
                    .order_by(RiskDriftEventRow.created_at.desc(), RiskDriftEventRow.id.desc())
                    .limit(1)
                )
                for _delivery, event_row, _user in rows
            }
            verification_by_user = {
                row.user_id: row for row in session.scalars(
                    select(EmailVerificationRow).where(
                        EmailVerificationRow.user_id.in_({user.id for _delivery, _event, user in rows})
                    )
                )
            }

        for _delivery, event_row, user in rows:
            if latest_event_by_coin.get(event_row.coin_id) != event_row.id:
                continue
            verification = verification_by_user.get(user.id)
            if verification is not None and verification.verified_at is None:
                continue
            event_created_at = event_row.created_at
            if event_created_at.tzinfo is None:
                event_created_at = event_created_at.replace(tzinfo=UTC)
            event = RiskDriftEvent(
                id=event_row.id,
                coin_id=event_row.coin_id,
                symbol=event_row.symbol,
                previous_status=event_row.previous_status,
                current_status=event_row.current_status,
                severity=event_row.severity,
                title=event_row.title,
                message=event_row.message,
                created_at=event_created_at.isoformat(),
            )
            status = await self._attempt_drift_email(user, event)
            summary[status] += 1
        return summary

    async def _attempt_drift_email(self, user: UserRow, event: RiskDriftEvent) -> str:
        with self.database.session() as session:
            existing = session.scalar(
                select(RiskDriftDeliveryRow).where(
                    RiskDriftDeliveryRow.event_id == event.id,
                    RiskDriftDeliveryRow.user_id == user.id,
                    RiskDriftDeliveryRow.channel == "email",
                )
            )
            if existing is not None and existing.status in SUBMITTED_DRIFT_STATUSES | {"suppressed"}:
                return "deduplicated"

            cutoff = datetime.now(UTC) - timedelta(
                seconds=max(0, self.settings.risk_drift_email_cooldown_seconds)
            )
            recent_sent = session.scalar(
                select(RiskDriftDeliveryRow)
                .join(
                    RiskDriftEventRow,
                    RiskDriftEventRow.id == RiskDriftDeliveryRow.event_id,
                )
                .where(
                    RiskDriftDeliveryRow.user_id == user.id,
                    RiskDriftDeliveryRow.channel == "email",
                    RiskDriftDeliveryRow.status.in_(SUBMITTED_DRIFT_STATUSES),
                    RiskDriftDeliveryRow.attempted_at >= cutoff,
                    RiskDriftEventRow.coin_id == event.coin_id,
                )
                .order_by(RiskDriftDeliveryRow.attempted_at.desc())
                .limit(1)
            )
            if recent_sent is not None:
                self._save_drift_delivery(
                    session,
                    existing=existing,
                    event_id=event.id,
                    user_id=user.id,
                    status="suppressed",
                    error_message=None,
                )
                logger.info(
                    "risk_drift_email_suppressed",
                    extra={"event_id": event.id, "user_id": user.id, "coin_id": event.coin_id},
                )
                return "suppressed"

        status = "failed"
        error_message = None
        error_type = None
        provider_message_id = None
        for delay in (0, 1, 3):
            if delay:
                await asyncio.sleep(delay)
            try:
                provider_message_id = await self._send_drift_email(user.email, event)
                status = "sent"
                error_message = None
                break
            except Exception as exc:  # A delivery failure must not stop model monitoring.
                error_message = str(exc)[:1000]
                error_type = type(exc).__name__

        with self.database.session() as session:
            existing = session.scalar(
                select(RiskDriftDeliveryRow).where(
                    RiskDriftDeliveryRow.event_id == event.id,
                    RiskDriftDeliveryRow.user_id == user.id,
                    RiskDriftDeliveryRow.channel == "email",
                )
            )
            self._save_drift_delivery(
                session,
                existing=existing,
                event_id=event.id,
                user_id=user.id,
                status=status,
                error_message=error_message,
                provider_message_id=provider_message_id,
            )
        log_method = logger.info if status == "sent" else logger.error
        log_method(
            "risk_drift_email_completed",
            extra={
                "delivery_status": status,
                "event_id": event.id,
                "user_id": user.id,
                "coin_id": event.coin_id,
                "error_type": error_type,
            },
        )
        return status

    @staticmethod
    def _save_drift_delivery(
        session,
        *,
        existing: RiskDriftDeliveryRow | None,
        event_id: int,
        user_id: int,
        status: str,
        error_message: str | None,
        provider_message_id: str | None = None,
    ) -> None:
        if existing is None:
            existing = RiskDriftDeliveryRow(
                event_id=event_id,
                user_id=user_id,
                channel="email",
                status=status,
                error_message=error_message,
                provider_message_id=provider_message_id,
            )
            session.add(existing)
        else:
            existing.status = status
            existing.error_message = error_message
            existing.attempted_at = datetime.now(UTC)
            existing.provider_message_id = provider_message_id
            existing.provider_event_at = None
        session.commit()

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
        error_type = None
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
                error_type = type(exc).__name__

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
        log_method = logger.info if status == "sent" else logger.error
        log_method(
            "notification_delivery_completed",
            extra={
                "channel": "email",
                "delivery_status": status,
                "event_id": event.id,
                "user_id": user_id,
                "error_type": error_type,
            },
        )

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

    async def _send_drift_email(self, recipient: str, event: RiskDriftEvent) -> str | None:
        self._require_configuration()
        review_url = f"{self.settings.public_app_url.rstrip('/')}/#risk-backtest"
        safe_review_url = html.escape(review_url, quote=True)
        message = self._base_message(
            recipient=recipient,
            subject=f"[ChainScope 模型监控] {event.title}",
            plain=(
                f"{event.title}\n\n{event.message}\n\n"
                f"资产：{event.symbol}\n"
                f"状态：{event.previous_status} → {event.current_status}\n"
                f"查看历史回测与漂移记录：{review_url}\n\n"
                "这是模型质量监控告警，不代表市场涨跌方向，也不构成投资建议。"
            ),
            html_body=(
                f"<h2 style='margin:0 0 16px;color:#9b5b00'>{html.escape(event.title)}</h2>"
                f"<p style='font-size:16px'>{html.escape(event.message)}</p>"
                f"<p><strong>资产：</strong>{html.escape(event.symbol)}<br>"
                f"<strong>状态：</strong>{html.escape(event.previous_status)} → "
                f"{html.escape(event.current_status)}</p>"
                f"<p><a href='{safe_review_url}'>查看历史回测与漂移记录</a></p>"
                "<p style='color:#667b74;font-size:12px'>这是模型质量监控告警，不代表市场涨跌方向，也不构成投资建议。</p>"
            ),
        )
        return await asyncio.to_thread(self._send_message_sync, message)

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

    def _send_message_sync(self, message: EmailMessage) -> str | None:
        self._require_configuration()
        if brevo_is_configured(self.settings):
            return self._send_via_brevo(message)
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
        return None

    def _send_via_brevo(self, message: EmailMessage) -> str | None:
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
        if not 200 <= response.status_code < 300:
            try:
                detail = str(response.json().get("message", "未知错误"))[:300]
            except (ValueError, AttributeError):
                detail = response.text[:300]
            raise RuntimeError(f"Brevo API 返回 {response.status_code}：{detail}")
        try:
            message_id = response.json().get("messageId")
        except (ValueError, AttributeError):
            message_id = None
        if isinstance(message_id, str):
            try:
                return normalize_brevo_message_id(message_id)
            except ValueError:
                logger.warning("brevo_message_id_unusable")
        return None
