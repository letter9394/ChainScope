import pytest

from app.models import DerivativesSnapshot, HistoryPoint
from app.services.risk import assess_risk, backtest_risk


def points(prices: list[float], volumes: list[float] | None = None) -> list[HistoryPoint]:
    volumes = volumes or [100.0] * len(prices)
    return [
        HistoryPoint(timestamp=index * 86_400_000, price=price, volume=volumes[index])
        for index, price in enumerate(prices)
    ]


def test_stable_prices_produce_low_risk() -> None:
    result = assess_risk(
        "bitcoin",
        "BTC",
        points([100, 101, 100.5, 101.2, 101.5, 102, 102.2, 102.5]),
    )

    assert result.level == "low"
    assert result.score < 30
    assert len(result.metrics) == 4


def test_sharp_drawdown_produces_high_risk() -> None:
    result = assess_risk(
        "bitcoin",
        "BTC",
        points([100, 125, 118, 92, 70, 63, 82, 55], [100, 90, 105, 140, 180, 210, 240, 500]),
    )

    assert result.level == "high"
    assert result.score >= 60


def test_volume_spike_increases_score() -> None:
    normal = assess_risk(
        "ethereum",
        "ETH",
        points([100, 101, 102, 103, 104, 105, 106, 107], [100] * 8),
    )
    spike = assess_risk(
        "ethereum",
        "ETH",
        points([100, 101, 102, 103, 104, 105, 106, 107], [100] * 7 + [400]),
    )

    assert spike.score > normal.score
    volume_metric = next(metric for metric in spike.metrics if metric.key == "volume")
    assert volume_metric.value == pytest.approx(4.0)


def test_requires_two_history_points() -> None:
    with pytest.raises(ValueError, match="At least two"):
        assess_risk("solana", "SOL", points([100]))


def test_rejects_non_positive_price_series() -> None:
    with pytest.raises(ValueError, match="positive prices"):
        assess_risk("solana", "SOL", points([0, 0, 0]))


def test_score_is_bounded() -> None:
    result = assess_risk(
        "solana",
        "SOL",
        points([100, 300, 20, 500, 5, 900, 2, 1], [1, 1, 1, 1, 1, 1, 1, 100]),
    )

    assert 0 <= result.score <= 100


def test_enhanced_model_adds_live_market_metrics() -> None:
    derivatives = DerivativesSnapshot(
        coin_id="bitcoin",
        symbol="BTC",
        available=True,
        funding_rate_percent=0.08,
        open_interest_change_5m_percent=8,
        long_short_ratio=3.0,
        long_account_percent=75,
        short_account_percent=25,
        fear_greed_value=90,
        fear_greed_label="Extreme Greed",
        updated_at="2026-09-21T00:00:00+00:00",
        source="test",
    )
    result = assess_risk(
        "bitcoin",
        "BTC",
        points([100, 101, 100.5, 101.2, 101.5, 102, 102.2, 102.5]),
        derivatives=derivatives,
    )

    keys = {metric.key for metric in result.metrics}
    assert {"funding_rate", "open_interest", "position_crowding", "fear_greed"} <= keys
    assert result.market_context == derivatives
    assert result.score == sum(metric.contribution for metric in result.metrics)


def test_backtest_measures_forward_drawdowns_after_new_high_risk_signal() -> None:
    history = points(
        [100] * 10 + [150, 100, 95, 80, 85, 75, 70, 72, 74],
        [100] * 11 + [400, 180, 170, 160, 150, 140, 130, 120],
    )

    result = backtest_risk(
        "bitcoin",
        "BTC",
        history,
        window_days=8,
        risk_threshold=60,
        hit_threshold_percent=3,
    )

    assert result.signal_count == 1
    assert result.recent_signals[0].score >= 60
    assert result.recent_signals[0].future_drawdowns == {
        "1": 5.0,
        "3": 20.0,
        "7": 30.0,
    }
    assert [item.hit_rate_percent for item in result.horizons] == [100.0, 100.0, 100.0]
    assert [item.worst_max_drawdown_percent for item in result.horizons] == [5.0, 20.0, 30.0]


def test_backtest_returns_zero_rates_when_no_high_risk_signal_occurs() -> None:
    history = points([100 + index * 0.1 for index in range(40)])

    result = backtest_risk("ethereum", "ETH", history, window_days=8)

    assert result.signal_count == 0
    assert all(item.samples == 0 for item in result.horizons)
    assert all(item.hit_rate_percent == 0 for item in result.horizons)
