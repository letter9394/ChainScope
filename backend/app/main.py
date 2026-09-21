import asyncio
import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.models import (
    AlertEvaluationResponse,
    AlertEvent,
    AlertRule,
    AlertRuleCreate,
    DerivativesSnapshot,
    HealthResponse,
    HistoryPoint,
    MarketCoin,
    NewsResponse,
    NewsTranslationRequest,
    NewsTranslationResponse,
    RiskAssessment,
    WatchlistItem,
)
from app.services.alerts import AlertRepository, evaluate_alert_rules
from app.services.derivatives import get_derivatives_snapshot
from app.services.market import CoinGeckoClient, MarketDataError, SUPPORTED_COINS
from app.services.news import get_news, translate_news
from app.services.risk import assess_risk
from app.services.watchlist import WatchlistRepository


app = FastAPI(
    title="ChainScope API",
    description="Market data and explainable cryptocurrency risk analysis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3100",
        "http://127.0.0.1:3100",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def get_market_client(settings: Settings = Depends(get_settings)) -> CoinGeckoClient:
    return CoinGeckoClient(settings)


def get_watchlist_repository(settings: Settings = Depends(get_settings)) -> WatchlistRepository:
    return WatchlistRepository(settings.database_path)


def get_alert_repository(settings: Settings = Depends(get_settings)) -> AlertRepository:
    return AlertRepository(settings.database_path)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.chain_scope_env,
        market_provider="Binance Spot/Futures + CoinGecko + Gold API + Alternative.me",
    )


@app.get("/api/markets", response_model=list[MarketCoin], tags=["market"])
async def markets(
    client: CoinGeckoClient = Depends(get_market_client),
) -> list[MarketCoin]:
    try:
        return await client.get_markets()
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/api/coins/{coin_id}/history",
    response_model=list[HistoryPoint],
    tags=["market"],
)
async def history(
    coin_id: str,
    days: int = Query(default=30, ge=7, le=365),
    client: CoinGeckoClient = Depends(get_market_client),
) -> list[HistoryPoint]:
    try:
        return await client.get_history(coin_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/api/coins/{coin_id}/risk",
    response_model=RiskAssessment,
    tags=["risk"],
)
async def risk(
    coin_id: str,
    days: int = Query(default=30, ge=7, le=365),
    client: CoinGeckoClient = Depends(get_market_client),
    settings: Settings = Depends(get_settings),
) -> RiskAssessment:
    try:
        history_points = await client.get_history(coin_id, days)
        derivatives_result, news_result = await asyncio.gather(
            get_derivatives_snapshot(settings, coin_id),
            get_news(settings=settings, coin_id=coin_id, limit=6),
            return_exceptions=True,
        )
        derivatives = derivatives_result if isinstance(derivatives_result, DerivativesSnapshot) else None
        articles = news_result.articles if isinstance(news_result, NewsResponse) else None
        return assess_risk(
            coin_id=coin_id,
            symbol=SUPPORTED_COINS[coin_id],
            history=history_points,
            derivatives=derivatives,
            news_articles=articles,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported coin: {coin_id}") from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/api/coins/{coin_id}/derivatives",
    response_model=DerivativesSnapshot,
    tags=["risk"],
)
async def derivatives(
    coin_id: str,
    settings: Settings = Depends(get_settings),
) -> DerivativesSnapshot:
    try:
        return await get_derivatives_snapshot(settings, coin_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/news", response_model=NewsResponse, tags=["news"])
async def news(
    coin_id: str | None = Query(default=None),
    limit: int = Query(default=6, ge=1, le=12),
    settings: Settings = Depends(get_settings),
) -> NewsResponse:
    try:
        return await get_news(settings=settings, coin_id=coin_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/news/translate", response_model=NewsTranslationResponse, tags=["news"])
async def translate_news_article(
    payload: NewsTranslationRequest,
    settings: Settings = Depends(get_settings),
) -> NewsTranslationResponse:
    try:
        return await translate_news(payload.title, payload.summary, settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/watchlist", response_model=list[WatchlistItem], tags=["watchlist"])
async def list_watchlist(
    repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> list[WatchlistItem]:
    return repository.list_items()


@app.post("/api/watchlist/{coin_id}", response_model=WatchlistItem, tags=["watchlist"])
async def add_watchlist(
    coin_id: str,
    repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> WatchlistItem:
    try:
        return repository.add(coin_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/watchlist/{coin_id}", status_code=204, tags=["watchlist"])
async def remove_watchlist(
    coin_id: str,
    repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> None:
    repository.remove(coin_id)


@app.get("/api/alerts/rules", response_model=list[AlertRule], tags=["alerts"])
async def list_alert_rules(
    repository: AlertRepository = Depends(get_alert_repository),
) -> list[AlertRule]:
    return repository.list_rules()


@app.post("/api/alerts/rules", response_model=AlertRule, status_code=201, tags=["alerts"])
async def create_alert_rule(
    payload: AlertRuleCreate,
    repository: AlertRepository = Depends(get_alert_repository),
) -> AlertRule:
    try:
        return repository.add_rule(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/alerts/rules/{rule_id}", status_code=204, tags=["alerts"])
async def remove_alert_rule(
    rule_id: int,
    repository: AlertRepository = Depends(get_alert_repository),
) -> None:
    if not repository.remove_rule(rule_id):
        raise HTTPException(status_code=404, detail="Alert rule not found")


@app.get("/api/alerts/events", response_model=list[AlertEvent], tags=["alerts"])
async def list_alert_events(
    unacknowledged_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    repository: AlertRepository = Depends(get_alert_repository),
) -> list[AlertEvent]:
    return repository.list_events(unacknowledged_only=unacknowledged_only, limit=limit)


@app.post(
    "/api/alerts/events/{event_id}/acknowledge",
    response_model=AlertEvent,
    tags=["alerts"],
)
async def acknowledge_alert_event(
    event_id: int,
    repository: AlertRepository = Depends(get_alert_repository),
) -> AlertEvent:
    event = repository.acknowledge_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Alert event not found")
    return event


@app.post("/api/alerts/evaluate", response_model=AlertEvaluationResponse, tags=["alerts"])
async def evaluate_alerts(
    repository: AlertRepository = Depends(get_alert_repository),
    client: CoinGeckoClient = Depends(get_market_client),
    settings: Settings = Depends(get_settings),
) -> AlertEvaluationResponse:
    try:
        return await evaluate_alert_rules(repository, client, settings)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


static_directory = os.getenv("STATIC_DIR")
if static_directory:
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="web")
