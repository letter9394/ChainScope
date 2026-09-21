import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.models import HistoryPoint, MarketCoin
from app.services.cache import cache


SUPPORTED_COINS: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
}
SUPPORTED_ASSETS: dict[str, str] = {**SUPPORTED_COINS, "gold": "XAU"}
BINANCE_SYMBOLS: dict[str, str] = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
}
FALLBACK_COIN_METADATA: dict[str, tuple[str, str]] = {
    "bitcoin": ("Bitcoin", "https://assets.coingecko.com/coins/images/1/large/bitcoin.png"),
    "ethereum": ("Ethereum", "https://assets.coingecko.com/coins/images/279/large/ethereum.png"),
    "solana": ("Solana", "https://assets.coingecko.com/coins/images/4128/large/solana.png"),
}


class MarketDataError(RuntimeError):
    """Raised when the upstream market provider is unavailable or invalid."""


class CoinGeckoClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "ChainScope/0.1"}
        if self.settings.coingecko_demo_api_key:
            headers["x-cg-demo-api-key"] = self.settings.coingecko_demo_api_key
        return headers

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    base_url=self.settings.coingecko_base_url,
                    timeout=self.settings.request_timeout_seconds,
                    headers=self._headers(),
                ) as client:
                    response = await client.get(path, params=params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.35 * (2**attempt))
        raise MarketDataError("Market data provider is temporarily unavailable") from last_error

    async def get_markets(self) -> list[MarketCoin]:
        crypto_markets = await self._get_crypto_markets()
        gold_market = await self._get_gold_market()
        return [*crypto_markets, *([gold_market] if gold_market is not None else [])]

    async def _get_crypto_markets(self) -> list[MarketCoin]:
        cache_key = "markets:usd:crypto"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            payload = await asyncio.wait_for(
                self._get(
                    "/coins/markets",
                    {
                        "vs_currency": "usd",
                        "ids": ",".join(SUPPORTED_COINS),
                        "order": "market_cap_desc",
                        "sparkline": "true",
                        "price_change_percentage": "24h,7d",
                    },
                ),
                timeout=min(8.0, self.settings.request_timeout_seconds),
            )
        except (TimeoutError, MarketDataError):
            last_good = cache.get("markets:usd:last-good")
            return last_good if last_good is not None else await self._get_binance_markets()

        if not isinstance(payload, list):
            return await self._get_binance_markets()

        markets = [
            MarketCoin(
                id=item["id"],
                symbol=str(item["symbol"]).upper(),
                name=item["name"],
                image=item.get("image"),
                current_price=float(item["current_price"]),
                market_cap=item.get("market_cap"),
                total_volume=item.get("total_volume"),
                price_change_percentage_24h=item.get("price_change_percentage_24h"),
                price_change_percentage_7d=item.get("price_change_percentage_7d_in_currency"),
                last_updated=item.get("last_updated"),
                sparkline=(item.get("sparkline_in_7d") or {}).get("price", []),
            )
            for item in payload
            if item.get("id") in SUPPORTED_COINS and item.get("current_price") is not None
        ]
        if len(markets) != len(SUPPORTED_COINS):
            return await self._get_binance_markets()
        cache.set(cache_key, markets, self.settings.market_cache_seconds)
        cache.set("markets:usd:last-good", markets, 3_600)
        return markets

    async def _get_binance_markets(self) -> list[MarketCoin]:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.binance_market_url,
                timeout=self.settings.request_timeout_seconds,
                headers={"Accept": "application/json", "User-Agent": "ChainScope/0.3"},
            ) as client:
                response = await client.get(
                    "/api/v3/ticker/24hr",
                    params={"symbols": '["BTCUSDT","ETHUSDT","SOLUSDT"]'},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataError("Market data providers are temporarily unavailable") from exc

        if not isinstance(payload, list):
            raise MarketDataError("Fallback market provider returned an unexpected response")

        try:
            markets: list[MarketCoin] = []
            for item in payload:
                coin_id = BINANCE_SYMBOLS.get(str(item.get("symbol")))
                if coin_id is None:
                    continue
                name, image = FALLBACK_COIN_METADATA[coin_id]
                markets.append(
                    MarketCoin(
                        id=coin_id,
                        symbol=SUPPORTED_COINS[coin_id],
                        name=name,
                        image=image,
                        current_price=float(item["lastPrice"]),
                        total_volume=float(item.get("quoteVolume") or 0),
                        price_change_percentage_24h=float(item.get("priceChangePercent") or 0),
                        last_updated=datetime_from_milliseconds(item.get("closeTime")),
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketDataError("Fallback market provider returned invalid data") from exc
        if len(markets) != len(SUPPORTED_COINS):
            raise MarketDataError("Fallback market provider returned incomplete data")

        order = {coin_id: index for index, coin_id in enumerate(SUPPORTED_COINS)}
        markets.sort(key=lambda market: order[market.id])
        cache.set("markets:usd:crypto", markets, self.settings.market_cache_seconds)
        cache.set("markets:usd:last-good", markets, 3_600)
        return markets

    async def _get_gold_market(self) -> MarketCoin | None:
        cache_key = "markets:usd:gold"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                headers={"Accept": "application/json", "User-Agent": "ChainScope/0.2"},
            ) as client:
                response = await client.get(self.settings.gold_api_url)
                response.raise_for_status()
                payload = response.json()
            price = float(payload["price"])
            if price <= 0:
                return None
            market = MarketCoin(
                id="gold",
                symbol="XAU",
                name="Gold Spot",
                current_price=price,
                last_updated=payload.get("updatedAt"),
            )
            cache.set(cache_key, market, self.settings.gold_cache_seconds)
            return market
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            # Gold is an additional feed; crypto quotes should stay available if it is down.
            return None

    async def get_history(self, coin_id: str, days: int) -> list[HistoryPoint]:
        if coin_id not in SUPPORTED_COINS:
            raise ValueError(f"Unsupported coin: {coin_id}")

        cache_key = f"history:{coin_id}:{days}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": "usd", "days": days, "interval": "daily"},
        )
        prices = payload.get("prices", []) if isinstance(payload, dict) else []
        volumes = payload.get("total_volumes", []) if isinstance(payload, dict) else []
        volume_by_timestamp = {int(item[0]): float(item[1]) for item in volumes}

        history = [
            HistoryPoint(
                timestamp=int(item[0]),
                price=float(item[1]),
                volume=volume_by_timestamp.get(int(item[0])),
            )
            for item in prices
            if isinstance(item, list) and len(item) >= 2
        ]
        if len(history) < 2:
            raise MarketDataError("Not enough historical data was returned")

        cache.set(cache_key, history, self.settings.history_cache_seconds)
        return history


def datetime_from_milliseconds(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()
