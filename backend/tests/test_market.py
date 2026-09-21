import pytest

from app.config import Settings
from app.models import MarketCoin
from app.services.cache import cache
from app.services.market import CoinGeckoClient, MarketDataError, datetime_from_milliseconds


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
