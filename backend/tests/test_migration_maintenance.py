from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_migration_maintenance_blocks_reads_and_writes_without_csrf() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        migration_read_only=True,
        background_alerts_enabled=True,
        risk_drift_monitor_enabled=True,
    )
    try:
        client = TestClient(app)
        for response in (
            client.get("/api/auth/csrf"),
            client.post("/api/auth/register", json={"email": "test@example.com"}),
            client.get("/api/nonexistent-migration-check"),
        ):
            assert response.status_code == 503
            assert response.headers["retry-after"] == "120"
            assert response.headers["x-chainscope-maintenance"] == "1"
            assert response.headers["x-request-id"]
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_migration_maintenance_keeps_health_check_available() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        migration_read_only=True,
        background_alerts_enabled=True,
        risk_drift_monitor_enabled=True,
    )
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["background_alerts"] is False
    assert payload["checks"]["scheduler"]["status"] == "disabled"
    assert payload["checks"]["risk_drift"]["status"] == "disabled"
