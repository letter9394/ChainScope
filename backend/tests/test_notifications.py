from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import Database
from app.main import _last_test_email_sent, app, get_database
from app.services.notifications import (
    NotificationService,
    email_is_configured,
    email_provider,
    masked_email,
)


def configured_settings() -> Settings:
    return Settings(
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_username="sender@qq.com",
        smtp_password="mail-client-authorization-code",
        smtp_from_email="sender@qq.com",
        smtp_security="ssl",
    )


def test_recognizes_mainland_email_provider() -> None:
    settings = configured_settings()

    assert email_is_configured(settings) is True
    assert email_provider(settings) == "QQ 邮箱"
    assert masked_email(settings.smtp_from_email) == "se***@qq.com"


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
    monkeypatch.setattr(NotificationService, "_send_message_sync", lambda self, message: None)
    _last_test_email_sent.clear()
    client = TestClient(app)
    try:
        client.post(
            "/api/auth/register",
            json={"email": "recipient@163.com", "password": "safe-password-4"},
        )
        enabled = client.put("/api/notifications/settings", json={"email_enabled": True})
        sent = client.post("/api/notifications/test-email")
        throttled = client.post("/api/notifications/test-email")

        assert enabled.status_code == 200
        assert enabled.json()["email_provider"] == "QQ 邮箱"
        assert sent.status_code == 200
        assert sent.json()["recipient"] == "recipient@163.com"
        assert throttled.status_code == 429
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)
        _last_test_email_sent.clear()
