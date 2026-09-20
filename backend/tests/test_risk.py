import pytest

from app.models import HistoryPoint
from app.services.risk import assess_risk


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

