import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import Settings
from app.models import CandlePoint, CandleSeries, HistoryPoint, MarketCoin
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
COIN_BINANCE_SYMBOLS: dict[str, str] = {
    coin_id: symbol for symbol, coin_id in BINANCE_SYMBOLS.items()
}
CANDLE_BINANCE_SYMBOLS: dict[str, str] = {
    **COIN_BINANCE_SYMBOLS,
    "gold": "PAXGUSDT",
}
CANDLE_INTERVALS = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"})
MASSIVE_INTERVALS: dict[str, tuple[int, str, int]] = {
    "1m": (1, "minute", 3),
    "5m": (5, "minute", 7),
    "15m": (15, "minute", 14),
    "30m": (30, "minute", 21),
    "1h": (1, "hour", 45),
    "4h": (4, "hour", 180),
    "1d": (1, "day", 730),
    "1w": (1, "week", 730),
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

    def _binance_base_urls(self) -> list[str]:
        candidates = [
            self.settings.binance_market_url,
            *self.settings.binance_market_fallback_urls.split(","),
        ]
        return list(dict.fromkeys(url.strip().rstrip("/") for url in candidates if url.strip()))

    async def _get_binance(self, path: str, params: dict[str, Any]) -> tuple[Any, str]:
        last_error: Exception | None = None
        for base_url in self._binance_base_urls():
            try:
                async with httpx.AsyncClient(
                    base_url=base_url,
                    timeout=self.settings.request_timeout_seconds,
                    headers={"Accept": "application/json", "User-Agent": "ChainScope/0.6"},
                ) as client:
                    response = await client.get(path, params=params)
                    response.raise_for_status()
                    return response.json(), base_url
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
        raise MarketDataError("Binance market endpoints are temporarily unavailable") from last_error

    async def _get_massive(self, path: str, params: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.massive_api_url.rstrip("/"),
                timeout=self.settings.request_timeout_seconds,
                headers={"Accept": "application/json", "User-Agent": "ChainScope/0.8"},
            ) as client:
                response = await client.get(path, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                error_payload = exc.response.json()
                provider_message = str(
                    error_payload.get("message") or error_payload.get("error") or "request rejected"
                )
            except (TypeError, ValueError):
                provider_message = "request rejected"
            safe_message = provider_message
            if self.settings.massive_api_key:
                safe_message = safe_message.replace(self.settings.massive_api_key, "[redacted]")
            safe_message = safe_message[:160]
            raise MarketDataError(f"Massive HTTP {status}: {safe_message}") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise MarketDataError("Massive connection or response error") from exc

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
            payload, _ = await self._get_binance(
                "/api/v3/ticker/24hr",
                {"symbols": '["BTCUSDT","ETHUSDT","SOLUSDT"]'},
            )
        except MarketDataError as exc:
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

        try:
            payload = await self._get(
                f"/coins/{coin_id}/market_chart",
                {"vs_currency": "usd", "days": days, "interval": "daily"},
            )
        except MarketDataError:
            return await self._get_binance_history(coin_id, days)
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
            return await self._get_binance_history(coin_id, days)

        cache.set(cache_key, history, self.settings.history_cache_seconds)
        return history

    async def _get_binance_history(self, coin_id: str, days: int) -> list[HistoryPoint]:
        symbol = COIN_BINANCE_SYMBOLS[coin_id]
        try:
            payload, _ = await self._get_binance(
                "/api/v3/klines",
                {"symbol": symbol, "interval": "1d", "limit": days},
            )
        except MarketDataError as exc:
            raise MarketDataError("Historical market data providers are temporarily unavailable") from exc

        try:
            history = [
                HistoryPoint(
                    timestamp=int(row[0]),
                    price=float(row[4]),
                    volume=float(row[7]),
                )
                for row in payload
                if isinstance(row, list) and len(row) >= 8
            ]
        except (TypeError, ValueError) as exc:
            raise MarketDataError("Fallback history provider returned invalid data") from exc
        if len(history) < 2:
            raise MarketDataError("Fallback history provider returned incomplete data")

        cache.set(f"history:{coin_id}:{days}", history, self.settings.history_cache_seconds)
        return history

    async def get_candles(self, asset_id: str, interval: str, limit: int) -> CandleSeries:
        if asset_id not in CANDLE_BINANCE_SYMBOLS:
            raise ValueError(f"Unsupported asset: {asset_id}")
        if interval not in CANDLE_INTERVALS:
            raise ValueError(f"Unsupported candle interval: {interval}")

        cache_key = f"candles:{asset_id}:{interval}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        massive_failure_reason: str | None = None
        if asset_id == "gold" and self.settings.massive_api_key:
            try:
                series = await self._get_massive_gold_candles(interval, limit)
                cache.set(cache_key, series, self.settings.gold_candle_cache_seconds)
                cache.set(f"{cache_key}:massive-last-good", series, 3_600)
                return series
            except MarketDataError as exc:
                massive_failure_reason = str(exc)
                last_exact = cache.get(f"{cache_key}:massive-last-good")
                if last_exact is not None:
                    return last_exact

        symbol = CANDLE_BINANCE_SYMBOLS[asset_id]
        try:
            payload, binance_base_url = await self._get_binance(
                "/api/v3/klines",
                {"symbol": symbol, "interval": interval, "limit": limit},
            )
            candles = parse_binance_candles(payload)
            if len(candles) < 2:
                raise ValueError("Incomplete candle response")
        except (MarketDataError, TypeError, ValueError) as exc:
            last_good = cache.get(f"{cache_key}:last-good")
            if last_good is not None:
                return last_good
            raise MarketDataError("Binance candle data is temporarily unavailable") from exc

        is_proxy = asset_id == "gold"
        series = CandleSeries(
            asset_id=asset_id,
            symbol=symbol,
            display_symbol="PAXG/USDT" if is_proxy else symbol.replace("USDT", "/USDT"),
            interval=interval,
            provider="Binance.US Spot" if "binance.us" in binance_base_url else "Binance Spot",
            is_proxy=is_proxy,
            proxy_notice=(
                (
                    f"Massive XAU/USD 暂不可用（{massive_failure_reason}），已自动降级为 "
                    "PAXG/USDT 黄金代币行情；它不等同于现货 XAU/USD。"
                )
                if massive_failure_reason else
                "当前 K 线使用 PAXG/USDT 黄金代币行情作为 XAU 走势代理，不等同于现货 XAU/USD。"
                if is_proxy else None
            ),
            updated_at=datetime.now(UTC).isoformat(),
            candles=candles,
        )
        cache_seconds = (
            self.settings.gold_candle_cache_seconds
            if asset_id == "gold"
            else self.settings.candle_cache_seconds
        )
        cache.set(cache_key, series, cache_seconds)
        cache.set(f"{cache_key}:last-good", series, 3_600)
        return series

    async def _get_massive_gold_candles(self, interval: str, limit: int) -> CandleSeries:
        api_key = self.settings.massive_api_key
        if not api_key:
            raise MarketDataError("Massive API key is not configured")

        multiplier, timespan, lookback_days = MASSIVE_INTERVALS[interval]
        # Massive Basic exposes minute aggregates only after the trading day is
        # finalized. Keep a two-day safety gap so the free tier never requests
        # a current-day range (which returns HTTP 403). Paid real-time plans can
        # set MASSIVE_DATA_DELAY_DAYS=0.
        delay_days = max(0, self.settings.massive_data_delay_days)
        end_date = datetime.now(UTC).date() - timedelta(days=delay_days)
        start_date = end_date - timedelta(days=lookback_days)
        path = (
            f"/v2/aggs/ticker/C:XAUUSD/range/{multiplier}/{timespan}/"
            f"{start_date.isoformat()}/{end_date.isoformat()}"
        )
        try:
            payload = await self._get_massive(
                path,
                {
                    "adjusted": "true",
                    "sort": "desc",
                    "limit": limit,
                    "apiKey": api_key,
                },
            )
            if not isinstance(payload, dict):
                raise MarketDataError("Massive returned a non-object response")
            if not isinstance(payload.get("results"), list):
                provider_status = str(payload.get("status") or "UNKNOWN")[:60]
                provider_message = str(
                    payload.get("message") or payload.get("error") or "results field is missing"
                )
                if api_key:
                    provider_message = provider_message.replace(api_key, "[redacted]")
                raise MarketDataError(
                    f"Massive payload {provider_status}: {provider_message[:160]}"
                )
            candles = parse_massive_candles(payload)
            if len(candles) < 2:
                results_count = payload.get("resultsCount", len(candles))
                raise MarketDataError(
                    f"Massive returned only {results_count} XAU/USD candle(s) for this range"
                )
        except MarketDataError:
            raise
        except (TypeError, ValueError) as exc:
            raise MarketDataError("Massive XAU/USD candles are temporarily unavailable") from exc

        return CandleSeries(
            asset_id="gold",
            symbol="C:XAUUSD",
            display_symbol="XAU/USD",
            interval=interval,
            provider="Massive Forex",
            is_proxy=False,
            proxy_notice=(
                f"现货 XAU/USD 聚合报价；当前按 Massive 免费方案延迟 {delay_days} 天读取，"
                "不等同于交易所实时成交价。"
            ),
            updated_at=datetime.now(UTC).isoformat(),
            candles=candles,
        )


def datetime_from_milliseconds(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()


def parse_binance_candles(payload: Any) -> list[CandlePoint]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected candle response")
    candles: list[CandlePoint] = []
    for row in payload:
        if not isinstance(row, list) or len(row) < 6:
            continue
        open_price = float(row[1])
        high_price = float(row[2])
        low_price = float(row[3])
        close_price = float(row[4])
        volume = float(row[5])
        if min(open_price, high_price, low_price, close_price) <= 0 or volume < 0:
            continue
        candles.append(CandlePoint(
            time=int(row[0]) // 1_000,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        ))
    return candles


def parse_massive_candles(payload: Any) -> list[CandlePoint]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Unexpected Massive candle response")
    candles: list[CandlePoint] = []
    for row in payload["results"]:
        if not isinstance(row, dict):
            continue
        try:
            open_price = float(row["o"])
            high_price = float(row["h"])
            low_price = float(row["l"])
            close_price = float(row["c"])
            volume = float(row.get("v") or 0)
            timestamp = int(row["t"]) // 1_000
        except (KeyError, TypeError, ValueError):
            continue
        if min(open_price, high_price, low_price, close_price) <= 0 or volume < 0:
            continue
        candles.append(CandlePoint(
            time=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        ))
    candles.sort(key=lambda candle: candle.time)
    return candles
