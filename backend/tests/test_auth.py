from pathlib import Path
import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import Database
from app.main import _last_password_reset_requested, app, get_database
from app.services.notifications import NotificationService


@pytest.fixture
def clients(tmp_path: Path):
    database = Database(str(tmp_path / "auth.db"))
    settings = Settings(
        chain_scope_env="development",
        session_secret="test-secret-that-is-not-used-in-production",
        background_alerts_enabled=False,
    )
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    first = TestClient(app)
    second = TestClient(app)
    yield first, second
    app.dependency_overrides.pop(get_database, None)
    app.dependency_overrides.pop(get_settings, None)


def test_register_login_and_user_data_are_isolated(clients) -> None:
    first, second = clients

    created = first.post(
        "/api/auth/register",
        json={"email": "first@example.com", "password": "safe-password-1"},
    )
    assert created.status_code == 201
    assert first.post("/api/watchlist/bitcoin").status_code == 200
    assert first.post(
        "/api/alerts/rules",
        json={"coin_id": "bitcoin", "metric": "risk_score", "operator": "gte", "threshold": 65},
    ).status_code == 201

    second.post(
        "/api/auth/register",
        json={"email": "second@example.com", "password": "safe-password-2"},
    )
    assert second.get("/api/watchlist").json() == []
    assert second.get("/api/alerts/rules").json() == []
    assert first.get("/api/watchlist").json()[0]["coin_id"] == "bitcoin"
    assert first.get("/api/alerts/rules").json()[0]["threshold"] == 65

    assert first.post("/api/auth/logout").status_code == 204
    assert first.get("/api/watchlist").status_code == 401
    assert first.post(
        "/api/auth/login",
        json={"email": "first@example.com", "password": "safe-password-1"},
    ).status_code == 200
    assert first.get("/api/auth/me").json()["email"] == "first@example.com"


def test_notification_settings_are_user_scoped(clients) -> None:
    first, _ = clients
    first.post(
        "/api/auth/register",
        json={"email": "alerts@example.com", "password": "safe-password-3"},
    )
    response = first.get("/api/notifications/settings")
    assert response.status_code == 200
    assert response.json()["in_app_enabled"] is True
    assert response.json()["schedule_seconds"] == 60
    assert response.json()["email_available"] is False
    assert response.json()["email_provider"] == "尚未配置"
    assert "telegram" not in response.json()

    enabled = first.put("/api/notifications/settings", json={"email_enabled": True})
    assert enabled.status_code == 409
    assert first.post("/api/notifications/test-email").status_code == 409


def test_rejects_bad_credentials(clients) -> None:
    first, _ = clients
    response = first.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "short"},
    )
    assert response.status_code == 422


def test_password_reset_email_preserves_account_data(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "password-reset.db"))
    settings = Settings(
        chain_scope_env="development",
        session_secret="password-reset-test-secret",
        background_alerts_enabled=False,
        public_app_url="https://chainscope.example",
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_security="ssl",
        smtp_username="sender@qq.com",
        smtp_password="authorization-code",
        smtp_from_email="sender@qq.com",
    )
    sent_messages = []
    monkeypatch.setattr(
        NotificationService,
        "_send_message_sync",
        lambda _service, message: sent_messages.append(message),
    )
    monkeypatch.setattr("app.main.monotonic", lambda: 10.0)
    _last_password_reset_requested.clear()
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    try:
        assert client.post(
            "/api/auth/register",
            json={"email": "recover@example.com", "password": "old-password-1"},
        ).status_code == 201
        assert client.post("/api/watchlist/bitcoin").status_code == 200
        assert client.post("/api/auth/logout").status_code == 204

        requested = client.post(
            "/api/auth/password-reset/request",
            json={"email": "recover@example.com"},
        )
        assert requested.status_code == 200
        assert len(sent_messages) == 1
        plain_body = sent_messages[0].get_body(preferencelist=("plain",)).get_content()
        match = re.search(r"reset_token=([^\s#]+)#account", plain_body)
        assert match is not None
        token = unquote(match.group(1))

        confirmed = client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "new-password-2"},
        )
        assert confirmed.status_code == 200
        assert client.get("/api/watchlist").json()[0]["coin_id"] == "bitcoin"
        assert client.post("/api/auth/logout").status_code == 204
        assert client.post(
            "/api/auth/login",
            json={"email": "recover@example.com", "password": "old-password-1"},
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={"email": "recover@example.com", "password": "new-password-2"},
        ).status_code == 200
        assert client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "another-password-3"},
        ).status_code == 400
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)
        _last_password_reset_requested.clear()
