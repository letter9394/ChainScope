from pathlib import Path

import pytest

from app.models import AlertRuleCreate, HistoryPoint, MarketCoin
from app.services.alerts import AlertRepository, evaluate_alert_rules


@pytest.fixture
def repository(tmp_path: Path) -> AlertRepository:
    return AlertRepository(str(tmp_path / "alerts.db"))


def test_rule_can_be_created_and_removed(repository: AlertRepository) -> None:
    created = repository.add_rule(
        AlertRuleCreate(
            coin_id="bitcoin",
            metric="risk_score",
            operator="gte",
            threshold=65,
        )
    )

    assert created.symbol == "BTC"
    assert repository.list_rules()[0].threshold == 65
    assert repository.remove_rule(created.id) is True
    assert repository.list_rules() == []


def test_alert_only_fires_on_safe_to_triggered_transition(repository: AlertRepository) -> None:
    rule = repository.add_rule(
        AlertRuleCreate(
            coin_id="bitcoin",
            metric="price_change_24h",
            operator="lte",
            threshold=-5,
        )
    )

    first = repository.evaluate({("bitcoin", "price_change_24h"): -7})
    duplicate = repository.evaluate({("bitcoin", "price_change_24h"): -8})
    repository.evaluate({("bitcoin", "price_change_24h"): -2})
    second = repository.evaluate({("bitcoin", "price_change_24h"): -6})

    assert first[0].rule_id == rule.id
    assert duplicate == []
    assert len(second) == 1
    assert len(repository.list_events()) == 2


def test_rule_can_be_paused_without_losing_history(repository: AlertRepository) -> None:
    rule = repository.add_rule(AlertRuleCreate(
        coin_id="bitcoin", metric="risk_score", operator="gte", threshold=65,
    ))
    assert len(repository.evaluate({("bitcoin", "risk_score"): 72})) == 1
    paused = repository.set_rule_enabled(rule.id, False)

    assert paused is not None and paused.enabled is False
    assert paused.is_triggered is True
    assert repository.list_events()[0].rule_id == rule.id
    assert repository.list_rules(enabled_only=True) == []
    assert repository.evaluate({("bitcoin", "risk_score"): 50}) == []
    assert len(repository.list_events()) == 1

    resumed = repository.set_rule_enabled(rule.id, True)
    assert resumed is not None and resumed.enabled is True
    assert repository.evaluate({("bitcoin", "risk_score"): 80}) == []
    repository.evaluate({("bitcoin", "risk_score"): 50})
    assert len(repository.evaluate({("bitcoin", "risk_score"): 70})) == 1
    assert len(repository.list_events()) == 2


def test_rule_status_update_is_user_scoped(repository: AlertRepository) -> None:
    rule = repository.add_rule(AlertRuleCreate(
        coin_id="bitcoin", metric="risk_score", operator="gte", threshold=65,
    ))
    other_user = AlertRepository(repository.database, user_id=2)
    assert other_user.set_rule_enabled(rule.id, False) is None
    assert repository.list_rules()[0].enabled is True


def test_event_can_be_acknowledged(repository: AlertRepository) -> None:
    repository.add_rule(
        AlertRuleCreate(
            coin_id="ethereum",
            metric="risk_score",
            operator="gte",
            threshold=60,
        )
    )
    event = repository.evaluate({("ethereum", "risk_score"): 78})[0]

    acknowledged = repository.acknowledge_event(event.id)

    assert acknowledged is not None
    assert acknowledged.acknowledged_at is not None
    assert repository.list_events(unacknowledged_only=True) == []


class FakeMarketClient:
    async def get_markets(self) -> list[MarketCoin]:
        return [
            MarketCoin(
                id="bitcoin",
                symbol="BTC",
                name="Bitcoin",
                current_price=65_000,
                price_change_percentage_24h=-6.5,
            )
        ]

    async def get_history(self, coin_id: str, days: int) -> list[HistoryPoint]:
        return [
            HistoryPoint(timestamp=index * 86_400_000, price=100 + index, volume=1_000)
            for index in range(max(8, days))
        ]


@pytest.mark.anyio
async def test_live_evaluation_collects_market_reading(repository: AlertRepository) -> None:
    repository.add_rule(
        AlertRuleCreate(
            coin_id="bitcoin",
            metric="price_change_24h",
            operator="lte",
            threshold=-5,
        )
    )

    result = await evaluate_alert_rules(repository, FakeMarketClient())  # type: ignore[arg-type]

    assert result.evaluated_rules == 1
    assert result.triggered_events[0].observed_value == -6.5
    assert len(result.active_events) == 1
