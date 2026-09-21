import asyncio
import os
from contextlib import asynccontextmanager, suppress
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.database import Database, UserRow
from app.models import (
    AlertEvaluationResponse, AlertEvent, AlertRule, AlertRuleCreate, AuthCredentials,
    AuthUser, DerivativesSnapshot, HealthResponse, HistoryPoint, MarketCoin,
    NewsResponse, NewsTranslationRequest, NewsTranslationResponse,
    NotificationSettingsResponse, NotificationSettingsUpdate, RiskAssessment,
    WatchlistItem,
)
from app.services.alerts import AlertRepository, evaluate_alert_rules
from app.services.auth import (
    UserRepository, create_session_token, decode_session_token, user_model, verify_password,
)
from app.services.derivatives import get_derivatives_snapshot
from app.services.market import CoinGeckoClient, MarketDataError, SUPPORTED_COINS
from app.services.news import get_news, translate_news
from app.services.notifications import NotificationRepository, preference_response
from app.services.risk import assess_risk
from app.services.scheduler import run_alert_scheduler
from app.services.watchlist import WatchlistRepository


@lru_cache
def database_for_url(url: str) -> Database:
    return Database(url)


def get_database(settings: Settings = Depends(get_settings)) -> Database:
    return database_for_url(settings.resolved_database_url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    database = database_for_url(settings.resolved_database_url)
    scheduler_task = None
    if settings.background_alerts_enabled:
        scheduler_task = asyncio.create_task(run_alert_scheduler(database, settings))
    yield
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


app = FastAPI(
    title="ChainScope API",
    description="Market data, accounts, and explainable cryptocurrency risk alerts.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def get_market_client(settings: Settings = Depends(get_settings)) -> CoinGeckoClient:
    return CoinGeckoClient(settings)


def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> UserRow:
    token = request.cookies.get(settings.session_cookie_name)
    user_id = decode_session_token(token, settings.session_secret) if token else None
    user = UserRepository(database).get_by_id(user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def get_watchlist_repository(
    user: UserRow = Depends(get_current_user),
    database: Database = Depends(get_database),
) -> WatchlistRepository:
    return WatchlistRepository(database, user.id)


def get_alert_repository(
    user: UserRow = Depends(get_current_user),
    database: Database = Depends(get_database),
) -> AlertRepository:
    return AlertRepository(database, user.id)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.chain_scope_env,
        market_provider="Binance Spot/Futures + CoinGecko + Gold API + Alternative.me",
        database="postgresql" if settings.resolved_database_url.startswith("postgresql") else "sqlite",
        background_alerts=settings.background_alerts_enabled,
    )


@app.post("/api/auth/register", response_model=AuthUser, status_code=201, tags=["auth"])
async def register(
    payload: AuthCredentials,
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthUser:
    repository = UserRepository(database)
    if repository.get_by_email(payload.email):
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    try:
        user = repository.create(payload.email, payload.password)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该邮箱已注册") from exc
    _set_session_cookie(response, user.id, settings)
    return user_model(user)


@app.post("/api/auth/login", response_model=AuthUser, tags=["auth"])
async def login(
    payload: AuthCredentials,
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthUser:
    user = UserRepository(database).get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _set_session_cookie(response, user.id, settings)
    return user_model(user)


def _set_session_cookie(response: Response, user_id: int, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(user_id, settings.session_secret, settings.session_max_age_seconds),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.chain_scope_env == "production",
        samesite="lax",
        path="/",
    )


@app.post("/api/auth/logout", status_code=204, tags=["auth"])
async def logout(response: Response, settings: Settings = Depends(get_settings)) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


@app.get("/api/auth/me", response_model=AuthUser, tags=["auth"])
async def current_user(user: UserRow = Depends(get_current_user)) -> AuthUser:
    return user_model(user)


@app.get("/api/markets", response_model=list[MarketCoin], tags=["market"])
async def markets(client: CoinGeckoClient = Depends(get_market_client)) -> list[MarketCoin]:
    try:
        return await client.get_markets()
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/coins/{coin_id}/history", response_model=list[HistoryPoint], tags=["market"])
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


@app.get("/api/coins/{coin_id}/risk", response_model=RiskAssessment, tags=["risk"])
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
        return assess_risk(
            coin_id=coin_id,
            symbol=SUPPORTED_COINS[coin_id],
            history=history_points,
            derivatives=derivatives_result if isinstance(derivatives_result, DerivativesSnapshot) else None,
            news_articles=news_result.articles if isinstance(news_result, NewsResponse) else None,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported coin: {coin_id}") from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/coins/{coin_id}/derivatives", response_model=DerivativesSnapshot, tags=["risk"])
async def derivatives(
    coin_id: str, settings: Settings = Depends(get_settings),
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
    payload: NewsTranslationRequest, settings: Settings = Depends(get_settings),
) -> NewsTranslationResponse:
    try:
        return await translate_news(payload.title, payload.summary, settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/watchlist", response_model=list[WatchlistItem], tags=["watchlist"])
async def list_watchlist(repository: WatchlistRepository = Depends(get_watchlist_repository)) -> list[WatchlistItem]:
    return repository.list_items()


@app.post("/api/watchlist/{coin_id}", response_model=WatchlistItem, tags=["watchlist"])
async def add_watchlist(
    coin_id: str, repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> WatchlistItem:
    try:
        return repository.add(coin_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/watchlist/{coin_id}", status_code=204, tags=["watchlist"])
async def remove_watchlist(
    coin_id: str, repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> None:
    repository.remove(coin_id)


@app.get("/api/alerts/rules", response_model=list[AlertRule], tags=["alerts"])
async def list_alert_rules(repository: AlertRepository = Depends(get_alert_repository)) -> list[AlertRule]:
    return repository.list_rules()


@app.post("/api/alerts/rules", response_model=AlertRule, status_code=201, tags=["alerts"])
async def create_alert_rule(
    payload: AlertRuleCreate, repository: AlertRepository = Depends(get_alert_repository),
) -> AlertRule:
    try:
        return repository.add_rule(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/alerts/rules/{rule_id}", status_code=204, tags=["alerts"])
async def remove_alert_rule(
    rule_id: int, repository: AlertRepository = Depends(get_alert_repository),
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


@app.post("/api/alerts/events/{event_id}/acknowledge", response_model=AlertEvent, tags=["alerts"])
async def acknowledge_alert_event(
    event_id: int, repository: AlertRepository = Depends(get_alert_repository),
) -> AlertEvent:
    event = repository.acknowledge_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Alert event not found")
    return event


@app.post("/api/alerts/evaluate", response_model=AlertEvaluationResponse, tags=["alerts"])
async def evaluate_alerts(
    user: UserRow = Depends(get_current_user),
    repository: AlertRepository = Depends(get_alert_repository),
    client: CoinGeckoClient = Depends(get_market_client),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AlertEvaluationResponse:
    try:
        result = await evaluate_alert_rules(repository, client, settings)
        from app.services.notifications import NotificationService
        await NotificationService(database, settings).deliver(user.id, result.triggered_events)
        return result
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/notifications/settings", response_model=NotificationSettingsResponse, tags=["notifications"])
async def get_notification_settings(
    user: UserRow = Depends(get_current_user),
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> NotificationSettingsResponse:
    return preference_response(NotificationRepository(database, user.id).get_or_create(), settings)


@app.put("/api/notifications/settings", response_model=NotificationSettingsResponse, tags=["notifications"])
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    user: UserRow = Depends(get_current_user),
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> NotificationSettingsResponse:
    if payload.email_enabled and not (settings.smtp_host and settings.smtp_from_email):
        raise HTTPException(status_code=409, detail="管理员尚未配置邮件发送服务")
    if payload.telegram_enabled:
        if not settings.telegram_bot_token:
            raise HTTPException(status_code=409, detail="管理员尚未配置 Telegram Bot")
        if not payload.telegram_chat_id:
            raise HTTPException(status_code=422, detail="启用 Telegram 时必须填写 Chat ID")
    row = NotificationRepository(database, user.id).update(payload)
    return preference_response(row, settings)


static_directory = os.getenv("STATIC_DIR")
if static_directory:
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="web")
