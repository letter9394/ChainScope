import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.models import DerivativesSnapshot
from app.services.cache import cache


FUTURES_SYMBOLS: dict[str, str] = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
}
DISPLAY_SYMBOLS: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
}


def _iso_from_milliseconds(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()


async def _request_json(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> Any:
    response = await client.get(path, params=params)
    response.raise_for_status()
    return response.json()


async def get_derivatives_snapshot(settings: Settings, coin_id: str) -> DerivativesSnapshot:
    if coin_id not in FUTURES_SYMBOLS:
        raise ValueError(f"Unsupported derivatives asset: {coin_id}")

    cache_key = f"derivatives:{coin_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    symbol = FUTURES_SYMBOLS[coin_id]
    now = datetime.now(UTC).isoformat()
    headers = {"Accept": "application/json", "User-Agent": "ChainScope/0.4"}
    try:
        async with httpx.AsyncClient(
            base_url=settings.binance_futures_url,
            timeout=settings.request_timeout_seconds,
            headers=headers,
        ) as futures_client, httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers=headers,
        ) as sentiment_client:
            results = await asyncio.gather(
                _request_json(futures_client, "/fapi/v1/premiumIndex", {"symbol": symbol}),
                _request_json(
                    futures_client,
                    "/futures/data/openInterestHist",
                    {"symbol": symbol, "period": "5m", "limit": 2},
                ),
                _request_json(
                    futures_client,
                    "/futures/data/globalLongShortAccountRatio",
                    {"symbol": symbol, "period": "5m", "limit": 1},
                ),
                _request_json(sentiment_client, settings.fear_greed_url, {"limit": 1, "format": "json"}),
                return_exceptions=True,
            )
    except httpx.HTTPError:
        results = []

    premium = results[0] if len(results) > 0 and isinstance(results[0], dict) else {}
    interest = results[1] if len(results) > 1 and isinstance(results[1], list) else []
    ratio_rows = results[2] if len(results) > 2 and isinstance(results[2], list) else []
    fear_payload = results[3] if len(results) > 3 and isinstance(results[3], dict) else {}

    try:
        funding_rate_percent = float(premium["lastFundingRate"]) * 100
        mark_price = float(premium["markPrice"])
        next_funding_time = _iso_from_milliseconds(premium.get("nextFundingTime"))
    except (KeyError, TypeError, ValueError):
        funding_rate_percent = None
        mark_price = None
        next_funding_time = None

    open_interest_usd: float | None = None
    open_interest_change: float | None = None
    try:
        if interest:
            open_interest_usd = float(interest[-1]["sumOpenInterestValue"])
        if len(interest) >= 2:
            previous = float(interest[-2]["sumOpenInterestValue"])
            current = float(interest[-1]["sumOpenInterestValue"])
            if previous > 0:
                open_interest_change = ((current / previous) - 1) * 100
    except (KeyError, TypeError, ValueError):
        open_interest_usd = None
        open_interest_change = None

    try:
        ratio = ratio_rows[-1]
        long_short_ratio = float(ratio["longShortRatio"])
        long_account_percent = float(ratio["longAccount"]) * 100
        short_account_percent = float(ratio["shortAccount"]) * 100
    except (IndexError, KeyError, TypeError, ValueError):
        long_short_ratio = None
        long_account_percent = None
        short_account_percent = None

    try:
        fear_row = fear_payload["data"][0]
        fear_greed_value = int(fear_row["value"])
        fear_greed_label = str(fear_row["value_classification"])
    except (IndexError, KeyError, TypeError, ValueError):
        fear_greed_value = None
        fear_greed_label = None

    snapshot = DerivativesSnapshot(
        coin_id=coin_id,
        symbol=DISPLAY_SYMBOLS[coin_id],
        available=any(
            value is not None
            for value in (funding_rate_percent, open_interest_usd, long_short_ratio)
        ),
        funding_rate_percent=round(funding_rate_percent, 6) if funding_rate_percent is not None else None,
        annualized_funding_percent=round(funding_rate_percent * 3 * 365, 2) if funding_rate_percent is not None else None,
        mark_price=round(mark_price, 8) if mark_price is not None else None,
        next_funding_time=next_funding_time,
        open_interest_usd=round(open_interest_usd, 2) if open_interest_usd is not None else None,
        open_interest_change_5m_percent=round(open_interest_change, 4) if open_interest_change is not None else None,
        long_short_ratio=round(long_short_ratio, 4) if long_short_ratio is not None else None,
        long_account_percent=round(long_account_percent, 2) if long_account_percent is not None else None,
        short_account_percent=round(short_account_percent, 2) if short_account_percent is not None else None,
        fear_greed_value=fear_greed_value,
        fear_greed_label=fear_greed_label,
        updated_at=now,
        source="Binance Futures + Alternative.me",
    )
    cache.set(cache_key, snapshot, settings.derivatives_cache_seconds)
    return snapshot
