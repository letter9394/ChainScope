import pytest

from app.config import Settings
from app.models import HistoryPoint, MarketCoin
from app.services.cache import cache
from app.services.market import (
    CoinGeckoClient, MarketDataError, datetime_from_milliseconds, parse_binance_candles,
)


@pytest.mark.anyio
async def test_market_snapshot_falls_back_when_coingecko_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.clear()
    client = CoinGeckoClient(Settings())
    fallback = [
        MarketCoin(id="bitcoin", symbol="BTC", name="Bitcoin", current_price=80_000),
        MarketCoin(id="ethereum", symbol="ETH", name="Ethereum", current_price=2_500),
        MarketCoin(id="solana", symbol="SOL", name="Solana", current_price=110),
    ]

    async def unavailable(path: str, params: dict[str, object]) -> object:
        raise MarketDataError("CoinGecko unavailable")

    async def binance_snapshot() -> list[MarketCoin]:
        return fallback

    async def no_gold() -> None:
        return None

    monkeypatch.setattr(client, "_get", unavailable)
    monkeypatch.setattr(client, "_get_binance_markets", binance_snapshot)
    monkeypatch.setattr(client, "_get_gold_market", no_gold)

    result = await client.get_markets()

    assert [market.symbol for market in result] == ["BTC", "ETH", "SOL"]


def test_binance_timestamp_is_normalized_to_iso_utc() -> None:
    assert datetime_from_milliseconds(0) == "1970-01-01T00:00:00+00:00"
    assert datetime_from_milliseconds(None) is None


def test_binance_candles_are_normalized_for_the_chart() -> None:
    result = parse_binance_candles([
        [1_700_000_000_000, "100", "105", "98", "103", "42", 0, "0"],
        [1_700_000_060_000, "103", "106", "101", "104", "51", 0, "0"],
    ])

    assert len(result) == 2
    assert result[0].time == 1_700_000_000
    assert result[0].open == 100
    assert result[0].high == 105
    assert result[0].low == 98
    assert result[0].close == 103
    assert result[0].volume == 42


def test_binance_endpoint_fallbacks_are_ordered_and_deduplicated() -> None:
    settings = Settings(
        binance_market_url="https://primary.example/",
        binance_market_fallback_urls=(
            "https://primary.example,https://secondary.example,https://api.binance.us"
        ),
    )

    assert CoinGeckoClient(settings)._binance_base_urls() == [
        "https://primary.example",
        "https://secondary.example",
        "https://api.binance.us",
    ]


@pytest.mark.anyio
async def test_history_falls_back_to_binance_when_coingecko_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.clear()
    client = CoinGeckoClient(Settings())
    fallback = [
        HistoryPoint(timestamp=1, price=100, volume=1_000),
        HistoryPoint(timestamp=2, price=102, volume=1_200),
    ]

    async def unavailable(path: str, params: dict[str, object]) -> object:
        raise MarketDataError("CoinGecko unavailable")

    async def binance_history(coin_id: str, days: int) -> list[HistoryPoint]:
        assert coin_id == "bitcoin"
        assert days == 30
        return fallback

    monkeypatch.setattr(client, "_get", unavailable)
    monkeypatch.setattr(client, "_get_binance_history", binance_history)

    assert await client.get_history("bitcoin", 30) == fallback
