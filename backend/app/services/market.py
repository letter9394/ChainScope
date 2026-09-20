import asyncio
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
        cache_key = "markets:usd:core"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._get(
            "/coins/markets",
            {
                "vs_currency": "usd",
                "ids": ",".join(SUPPORTED_COINS),
                "order": "market_cap_desc",
                "sparkline": "true",
                "price_change_percentage": "24h,7d",
            },
        )
        if not isinstance(payload, list):
            raise MarketDataError("Market provider returned an unexpected response")

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
        gold_market = await self._get_gold_market()
        if gold_market is not None:
            markets.append(gold_market)
        cache.set(cache_key, markets, self.settings.market_cache_seconds)
        return markets

    async def _get_gold_market(self) -> MarketCoin | None:
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
            return MarketCoin(
                id="gold",
                symbol="XAU",
                name="Gold Spot",
                current_price=price,
                last_updated=payload.get("updatedAt"),
            )
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
