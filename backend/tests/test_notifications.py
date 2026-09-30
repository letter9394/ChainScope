from email.message import EmailMessage
from datetime import UTC, datetime
from pathlib import Path
import re
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from app.config import Settings, get_settings
from app.database import (
    Database, EmailVerificationRow, NotificationPreferenceRow,
    RiskDriftDeliveryRow, RiskDriftEventRow, UserRow,
)
from app.main import _last_test_email_sent, app, get_database
from app.services.notifications import (
    NotificationService,
    email_is_configured,
    email_provider,
    masked_email,
)
from tests.support import CsrfTestClient


def configured_settings() -> Settings:
    return Settings(
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_username="sender@qq.com",
        smtp_password="mail-client-authorization-code",
        smtp_from_email="sender@qq.com",
        smtp_security="ssl",
    )


def configured_brevo_settings() -> Settings:
    return Settings(
        brevo_api_key="xkeysib-test-key",
        brevo_sender_email="sender@qq.com",
    )


def test_recognizes_mainland_email_provider() -> None:
    settings = configured_settings()

    assert email_is_configured(settings) is True
    assert email_provider(settings) == "QQ 邮箱"
    assert masked_email(settings.smtp_from_email) == "se***@qq.com"


@pytest.mark.anyio
async def test_brevo_https_api_is_preferred_and_receives_email(tmp_path: Path, monkeypatch) -> None:
    settings = configured_brevo_settings()
    service = NotificationService(Database(str(tmp_path / "brevo.db")), settings)
    captured = {}

    class FakeResponse:
        status_code = 201
        text = ""

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.notifications.httpx.post", fake_post)
    await service.send_test_email("recipient@qq.com")

    assert email_is_configured(settings) is True
    assert email_provider(settings) == "Brevo HTTPS API"
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["api-key"] == "xkeysib-test-key"
    assert captured["json"]["sender"]["email"] == "sender@qq.com"
    assert captured["json"]["to"][0]["email"] == "recipient@qq.com"
    assert "邮箱通知测试成功" in captured["json"]["subject"]


@pytest.mark.anyio
async def test_test_email_contains_plain_and_html_parts(tmp_path: Path, monkeypatch) -> None:
    service = NotificationService(Database(str(tmp_path / "notifications.db")), configured_settings())
    captured: list[EmailMessage] = []
    monkeypatch.setattr(service, "_send_message_sync", captured.append)

    await service.send_test_email("recipient@163.com")

    assert len(captured) == 1
    assert captured[0]["To"] == "recipient@163.com"
    assert "邮箱通知测试成功" in str(captured[0]["Subject"])
    assert captured[0].is_multipart()


def test_rejects_unknown_smtp_security(tmp_path: Path) -> None:
    settings = configured_settings()
    settings.smtp_security = "unsafe"
    service = NotificationService(Database(str(tmp_path / "notifications.db")), settings)

    with pytest.raises(RuntimeError, match="SMTP_SECURITY"):
        service._require_configuration()


def test_logged_in_user_can_enable_and_test_email(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "notification-api.db"))
    settings = configured_settings()
    settings.session_secret = "notification-test-secret"
    settings.background_alerts_enabled = False
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    sent_messages = []
    monkeypatch.setattr(
        NotificationService,
        "_send_message_sync",
        lambda self, message: sent_messages.append(message),
    )
    monkeypatch.setattr("app.main.monotonic", lambda: 10.0)
    _last_test_email_sent.clear()
    client = CsrfTestClient(app)
    try:
        registered = client.post(
            "/api/auth/register",
            json={"email": "recipient@163.com", "password": "safe-password-4"},
        )
        assert registered.status_code == 201
        verification_body = sent_messages[0].get_body(preferencelist=("plain",)).get_content()
        match = re.search(r"verify_email_token=([^\s#]+)#account", verification_body)
        assert match is not None
        verified = client.post(
            "/api/auth/email-verification/confirm",
            json={"token": unquote(match.group(1))},
        )
        assert verified.status_code == 200
        enabled = client.put(
            "/api/notifications/settings",
            json={"email_enabled": True, "drift_email_enabled": True},
        )
        sent = client.post("/api/notifications/test-email")
        throttled = client.post("/api/notifications/test-email")

        assert enabled.status_code == 200
        assert enabled.json()["email_provider"] == "QQ 邮箱"
        assert enabled.json()["drift_email_enabled"] is True
        assert sent.status_code == 200
        assert sent.json()["recipient"] == "recipient@163.com"
        assert throttled.status_code == 429
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)
        _last_test_email_sent.clear()


@pytest.mark.anyio
async def test_drift_email_requires_opt_in_and_suppresses_repeat_for_asset(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "drift-notifications.db"))
    service = NotificationService(database, configured_settings())
    sent: list[EmailMessage] = []
    monkeypatch.setattr(service, "_send_message_sync", sent.append)

    with database.session() as session:
        subscribed = UserRow(email="subscribed@example.com", password_hash="hash")
        unverified = UserRow(email="unverified@example.com", password_hash="hash")
        opted_out = UserRow(email="optedout@example.com", password_hash="hash")
        session.add_all([subscribed, unverified, opted_out])
        session.flush()
        session.add_all([
            EmailVerificationRow(user_id=subscribed.id, verified_at=datetime.now(UTC)),
            EmailVerificationRow(user_id=unverified.id),
            EmailVerificationRow(user_id=opted_out.id, verified_at=datetime.now(UTC)),
            NotificationPreferenceRow(user_id=subscribed.id, drift_email_enabled=True),
            NotificationPreferenceRow(user_id=unverified.id, drift_email_enabled=True),
            NotificationPreferenceRow(user_id=opted_out.id, drift_email_enabled=False),
        ])
        first = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="stable",
            current_status="deteriorating", transition_date="2026-09-29",
            severity="warning", title="BTC 模型检测到性能衰减", message="需要复核",
        )
        session.add(first)
        session.commit()
        first_id = first.id

    from app.services.drift import RiskDriftRepository
    repository = RiskDriftRepository(database)
    first_event = repository.recent_events()[0]
    assert first_event.id == first_id
    assert await service.deliver_drift_events([first_event]) == {
        "sent": 1, "failed": 0, "suppressed": 0, "deduplicated": 0,
    }
    assert len(sent) == 1
    assert sent[0]["To"] == "subscribed@example.com"
    assert await service.deliver_drift_events([first_event]) == {
        "sent": 0, "failed": 0, "suppressed": 0, "deduplicated": 1,
    }
    assert len(sent) == 1

    with database.session() as session:
        second = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="mixed",
            current_status="deteriorating", transition_date="2026-09-30",
            severity="warning", title="BTC 模型再次衰减", message="需要复核",
        )
        session.add(second)
        session.commit()
        second_id = second.id

    second_event = next(event for event in repository.recent_events() if event.id == second_id)
    assert await service.deliver_drift_events([second_event]) == {
        "sent": 0, "failed": 0, "suppressed": 1, "deduplicated": 0,
    }
    assert len(sent) == 1
    with database.session() as session:
        deliveries = list(session.scalars(
            select(RiskDriftDeliveryRow).order_by(RiskDriftDeliveryRow.event_id)
        ))
    assert [(row.event_id, row.status) for row in deliveries] == [
        (first_id, "sent"), (second_id, "suppressed"),
    ]
