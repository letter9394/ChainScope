from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import Database
from app.main import app, get_database


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


def test_rejects_bad_credentials(clients) -> None:
    first, _ = clients
    response = first.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "short"},
    )
    assert response.status_code == 422
