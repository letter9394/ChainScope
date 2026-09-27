from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import Database
from app.main import app, get_database
from app.services.csrf import create_csrf_token, validate_csrf_token


def test_csrf_token_is_signed_and_set_as_a_host_cookie(tmp_path: Path) -> None:
    settings = Settings(
        chain_scope_env="production",
        session_secret="csrf-production-test-secret",
        public_app_url="https://chainscope.example",
        background_alerts_enabled=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).get("/api/auth/csrf")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    token = response.json()["csrf_token"]
    set_cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert validate_csrf_token(token, settings.session_secret, settings.csrf_max_age_seconds)
    assert "chainscope_csrf=" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "domain=" not in set_cookie
    assert response.headers["cache-control"] == "no-store"


def test_unsafe_request_without_csrf_token_is_rejected() -> None:
    response = TestClient(app).post(
        "/api/auth/register",
        json={"email": "blocked@example.com", "password": "safe-password-1"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"
    assert response.headers["x-csrf-error"] == "1"


def test_csrf_rejection_exposes_retry_headers_to_local_frontend() -> None:
    response = TestClient(app).post(
        "/api/auth/login",
        headers={"Origin": "http://localhost:3100"},
        json={"email": "person@example.com", "password": "safe-password-1"},
    )

    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == "http://localhost:3100"
    exposed_headers = response.headers["access-control-expose-headers"].lower()
    assert "x-csrf-error" in exposed_headers
    assert "x-request-id" in exposed_headers


def test_valid_same_origin_csrf_token_allows_request(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "csrf.db"))
    settings = Settings(
        chain_scope_env="production",
        session_secret="csrf-request-test-secret",
        public_app_url="https://chainscope.example",
        background_alerts_enabled=False,
    )
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app, base_url="https://chainscope.example")
    try:
        token = client.get("/api/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/api/auth/register",
            headers={"Origin": "https://chainscope.example", "X-CSRF-Token": token},
            json={"email": "allowed@example.com", "password": "safe-password-2"},
        )
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 201


def test_cross_site_origin_is_rejected_even_with_valid_token() -> None:
    client = TestClient(app)
    token = client.get("/api/auth/csrf").json()["csrf_token"]

    response = client.post(
        "/api/auth/login",
        headers={
            "Origin": "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
            "X-CSRF-Token": token,
        },
        json={"email": "person@example.com", "password": "safe-password-3"},
    )

    assert response.status_code == 403
    assert response.headers["x-csrf-error"] == "1"


def test_mismatched_csrf_header_is_rejected() -> None:
    client = TestClient(app)
    client.get("/api/auth/csrf")

    response = client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": "different-token"},
        json={"email": "person@example.com", "password": "safe-password-4"},
    )

    assert response.status_code == 403


def test_expired_csrf_token_is_rejected() -> None:
    token = create_csrf_token("test-secret", issued_at=1_000)

    assert validate_csrf_token(token, "test-secret", 100, now=1_101) is False
    assert validate_csrf_token(token, "other-secret", 100, now=1_050) is False
