"""Exercise the complete in-app alert journey through the HTTP API."""

from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.database import Database
from app.main import app, get_database, get_market_client
from app.models import MarketCoin
from tests.support import CsrfTestClient


class ChangingMarketClient:
    def __init__(self) -> None:
        self.change_24h = -3.0

    async def get_markets(self) -> list[MarketCoin]:
        return [
            MarketCoin(
                id="bitcoin",
                symbol="BTC",
                name="Bitcoin",
                current_price=65_000,
                price_change_percentage_24h=self.change_24h,
            )
        ]


@pytest.fixture
def alert_client(tmp_path: Path):
    database = Database(str(tmp_path / "alert-journey.db"))
    market = ChangingMarketClient()
    settings = Settings(
        session_secret="alert-journey-test-secret",
        background_alerts_enabled=False,
    )
    previous_overrides = {
        dependency: app.dependency_overrides.get(dependency)
        for dependency in (get_database, get_market_client, get_settings)
    }
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_market_client] = lambda: market
    app.dependency_overrides[get_settings] = lambda: settings
    with CsrfTestClient(app) as client:
        yield client, market
    for dependency, previous in previous_overrides.items():
        if previous is None:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = previous


def test_rule_triggers_once_can_be_acknowledged_and_retriggers_after_reset(alert_client) -> None:
    client, market = alert_client
    registered = client.post(
        "/api/auth/register",
        json={"email": "alert-journey@example.com", "password": "safe-password-1"},
    )
    assert registered.status_code == 201

    created = client.post(
        "/api/alerts/rules",
        json={"coin_id": "bitcoin", "metric": "price_change_24h", "operator": "lte", "threshold": -5},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    # The initial safe reading establishes the baseline without a notification.
    assert client.post("/api/alerts/evaluate").json()["triggered_events"] == []
    assert client.get("/api/alerts/events").json() == []

    market.change_24h = -6.0
    first = client.post("/api/alerts/evaluate")
    assert first.status_code == 200
    assert len(first.json()["triggered_events"]) == 1
    event_id = first.json()["triggered_events"][0]["id"]
    assert first.json()["triggered_events"][0]["rule_id"] == rule_id

    # Repeated checks while still across the threshold must not duplicate it.
    assert client.post("/api/alerts/evaluate").json()["triggered_events"] == []
    assert len(client.get("/api/alerts/events").json()) == 1

    acknowledged = client.post(f"/api/alerts/events/{event_id}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged_at"] is not None
    assert client.get("/api/alerts/events?unacknowledged_only=true").json() == []
    assert len(client.get("/api/alerts/events").json()) == 1

    market.change_24h = -2.0
    assert client.post("/api/alerts/evaluate").json()["triggered_events"] == []
    market.change_24h = -7.0
    assert len(client.post("/api/alerts/evaluate").json()["triggered_events"]) == 1
    assert len(client.get("/api/alerts/events").json()) == 2

    # Deleting a rule also removes its associated events; the UI warns first.
    assert client.delete(f"/api/alerts/rules/{rule_id}").status_code == 204
    assert client.get("/api/alerts/rules").json() == []
    assert client.get("/api/alerts/events").json() == []


def test_identical_rule_is_rejected_without_affecting_other_rules_or_users(alert_client) -> None:
    client, _ = alert_client
    assert client.post(
        "/api/auth/register",
        json={"email": "first-alert-user@example.com", "password": "safe-password-1"},
    ).status_code == 201
    rule = {"coin_id": "bitcoin", "metric": "risk_score", "operator": "gte", "threshold": 0}

    first = client.post("/api/alerts/rules", json=rule)
    duplicate = client.post("/api/alerts/rules", json=rule)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "相同的预警规则已存在，请在下方查看已有规则。"
    assert [item["id"] for item in client.get("/api/alerts/rules").json()] == [first.json()["id"]]

    # A different threshold remains a distinct rule, and rules are scoped to each user.
    assert client.post("/api/alerts/rules", json={**rule, "threshold": 65}).status_code == 201
    assert client.post("/api/auth/logout").status_code == 204
    assert client.post(
        "/api/auth/register",
        json={"email": "second-alert-user@example.com", "password": "safe-password-1"},
    ).status_code == 201
    assert client.post("/api/alerts/rules", json=rule).status_code == 201
    assert len(client.get("/api/alerts/rules").json()) == 1
