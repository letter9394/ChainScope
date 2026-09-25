import asyncio
import hashlib
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from functools import lru_cache
from time import monotonic
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.database import Database, UserRow
from app.models import (
    AlertEvaluationResponse, AlertEvent, AlertRule, AlertRuleCreate, AuthCredentials,
    AuthMessageResponse, AuthUser, CandleSeries, DerivativesSnapshot,
    EmailVerificationConfirm, HealthResponse, HistoryPoint, MarketCoin,
    NewsResponse, NewsTranslationRequest, NewsTranslationResponse,
    NotificationSettingsResponse, NotificationSettingsUpdate, NotificationTestResponse,
    PasswordResetConfirm, PasswordResetRequest, PasswordResetRequestResponse, RiskAssessment,
    RiskBacktestResult, WatchlistItem,
)
from app.services.alerts import AlertRepository, evaluate_alert_rules
from app.services.auth import (
    UserRepository, create_email_verification_token, create_password_reset_token,
    create_session_token, decode_email_verification_token, decode_password_reset_token,
    decode_session_token, user_model, verify_password,
)
from app.services.derivatives import get_derivatives_snapshot
from app.services.market import CoinGeckoClient, MarketDataError, SUPPORTED_COINS
from app.services.news import get_news, translate_news
from app.services.notifications import (
    NotificationRepository, NotificationService, email_is_configured,
    email_provider, preference_response,
)
from app.services.risk import assess_risk, backtest_risk
from app.services.rate_limit import InMemoryRateLimiter
from app.services.scheduler import run_alert_scheduler
from app.services.watchlist import WatchlistRepository


_last_test_email_sent: dict[int, float] = {}
_auth_rate_limiter = InMemoryRateLimiter()


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


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded[:80] if forwarded else (request.client.host if request.client else "unknown")


def _enforce_auth_rate_limit(
    request: Request,
    *,
    action: str,
    account: str,
    limit: int,
    window_seconds: int,
) -> None:
    account_fingerprint = hashlib.sha256(
        account.strip().lower().encode("utf-8")
    ).hexdigest()[:24]
    keys = (
        f"auth:{action}:account:{account_fingerprint}",
        f"auth:{action}:ip:{_client_address(request)}",
    )
    for key in keys:
        decision = _auth_rate_limiter.check(
            key,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请在 {decision.retry_after_seconds} 秒后重试",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )


async def _send_email_verification(
    user: UserRow,
    database: Database,
    settings: Settings,
) -> None:
    token = create_email_verification_token(
        user,
        settings.session_secret,
        settings.email_verification_max_age_seconds,
    )
    verification_url = (
        f"{settings.public_app_url.rstrip('/')}/?verify_email_token={quote(token)}#account"
    )
    await NotificationService(database, settings).send_email_verification(
        user.email,
        verification_url,
    )


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.chain_scope_env,
        market_provider="Binance Spot/Futures/Klines + CoinGecko + Gold API + Alternative.me",
        database="postgresql" if settings.resolved_database_url.startswith("postgresql") else "sqlite",
        background_alerts=settings.background_alerts_enabled,
    )


@app.get("/api/assets/{asset_id}/candles", response_model=CandleSeries, tags=["market"])
async def asset_candles(
    asset_id: str,
    interval: str = Query(default="15m"),
    limit: int = Query(default=300, ge=2, le=1_000),
    client: CoinGeckoClient = Depends(get_market_client),
) -> CandleSeries:
    try:
        return await client.get_candles(asset_id, interval, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/auth/register", response_model=AuthUser, status_code=201, tags=["auth"])
async def register(
    request: Request,
    payload: AuthCredentials,
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthUser:
    _enforce_auth_rate_limit(
        request,
        action="register",
        account=payload.email,
        limit=settings.auth_register_limit,
        window_seconds=settings.auth_register_window_seconds,
    )
    repository = UserRepository(database)
    if repository.get_by_email(payload.email):
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    try:
        user = repository.create(payload.email, payload.password)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该邮箱已注册") from exc
    _set_session_cookie(response, user.id, settings)
    if email_is_configured(settings):
        try:
            await _send_email_verification(user, database, settings)
        except Exception:
            # Registration remains usable; the signed-in user can retry from the account panel.
            pass
    return user_model(user, email_verified=False)


@app.post("/api/auth/login", response_model=AuthUser, tags=["auth"])
async def login(
    request: Request,
    payload: AuthCredentials,
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthUser:
    _enforce_auth_rate_limit(
        request,
        action="login",
        account=payload.email,
        limit=settings.auth_login_limit,
        window_seconds=settings.auth_login_window_seconds,
    )
    repository = UserRepository(database)
    user = repository.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _set_session_cookie(response, user.id, settings)
    return user_model(user, email_verified=repository.is_email_verified(user.id))


@app.post(
    "/api/auth/password-reset/request",
    response_model=PasswordResetRequestResponse,
    tags=["auth"],
)
async def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> PasswordResetRequestResponse:
    generic_message = "如果该邮箱已注册，重置邮件将在几分钟内送达。"
    _enforce_auth_rate_limit(
        request,
        action="password-reset",
        account=payload.email,
        limit=settings.auth_password_reset_limit,
        window_seconds=settings.auth_password_reset_window_seconds,
    )

    user = UserRepository(database).get_by_email(payload.email)
    if user is None:
        return PasswordResetRequestResponse(message=generic_message)
    if not email_is_configured(settings):
        raise HTTPException(status_code=503, detail="邮件服务尚未配置完成，请稍后再试")

    token = create_password_reset_token(user, settings.session_secret, settings.password_reset_max_age_seconds)
    reset_url = f"{settings.public_app_url.rstrip('/')}/?reset_token={quote(token)}#account"
    try:
        await NotificationService(database, settings).send_password_reset_email(user.email, reset_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"重置邮件发送失败：{str(exc)[:240]}") from exc
    return PasswordResetRequestResponse(message=generic_message)


@app.post("/api/auth/password-reset/confirm", response_model=AuthUser, tags=["auth"])
async def confirm_password_reset(
    request: Request,
    payload: PasswordResetConfirm,
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthUser:
    _enforce_auth_rate_limit(
        request,
        action="password-reset-confirm",
        account=payload.token[-32:],
        limit=settings.auth_login_limit,
        window_seconds=settings.auth_login_window_seconds,
    )
    decoded = decode_password_reset_token(payload.token, settings.session_secret)
    if decoded is None:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期，请重新申请")
    user_id, fingerprint = decoded
    user = UserRepository(database).reset_password(user_id, fingerprint, payload.password)
    if user is None:
        raise HTTPException(status_code=400, detail="重置链接已使用或已失效，请重新申请")
    _set_session_cookie(response, user.id, settings)
    repository = UserRepository(database)
    return user_model(user, email_verified=repository.is_email_verified(user.id))


@app.post(
    "/api/auth/email-verification/confirm",
    response_model=AuthUser,
    tags=["auth"],
)
async def confirm_email_verification(
    request: Request,
    payload: EmailVerificationConfirm,
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthUser:
    _enforce_auth_rate_limit(
        request,
        action="email-verification-confirm",
        account=payload.token[-32:],
        limit=settings.auth_login_limit,
        window_seconds=settings.auth_login_window_seconds,
    )
    decoded = decode_email_verification_token(payload.token, settings.session_secret)
    if decoded is None:
        raise HTTPException(status_code=400, detail="验证链接无效或已过期，请重新发送")
    user_id, email_fingerprint = decoded
    user = UserRepository(database).verify_email(user_id, email_fingerprint)
    if user is None:
        raise HTTPException(status_code=400, detail="验证链接无效或账号已变更")
    _set_session_cookie(response, user.id, settings)
    return user_model(user, email_verified=True)


@app.post(
    "/api/auth/email-verification/resend",
    response_model=AuthMessageResponse,
    tags=["auth"],
)
async def resend_email_verification(
    request: Request,
    user: UserRow = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> AuthMessageResponse:
    repository = UserRepository(database)
    if repository.is_email_verified(user.id):
        return AuthMessageResponse(message="邮箱已经验证，无需重复发送。")
    _enforce_auth_rate_limit(
        request,
        action="email-verification-resend",
        account=user.email,
        limit=settings.auth_verification_resend_limit,
        window_seconds=settings.auth_verification_resend_window_seconds,
    )
    if not email_is_configured(settings):
        raise HTTPException(status_code=503, detail="邮件服务尚未配置完成，请稍后再试")
    try:
        await _send_email_verification(user, database, settings)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"验证邮件发送失败：{str(exc)[:240]}") from exc
    return AuthMessageResponse(message="验证邮件已发送，请检查收件箱和垃圾邮件文件夹。")


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
async def current_user(
    user: UserRow = Depends(get_current_user),
    database: Database = Depends(get_database),
) -> AuthUser:
    repository = UserRepository(database)
    return user_model(user, email_verified=repository.is_email_verified(user.id))


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


@app.get(
    "/api/coins/{coin_id}/risk/backtest",
    response_model=RiskBacktestResult,
    tags=["risk"],
)
async def risk_backtest(
    coin_id: str,
    days: int = Query(default=365, ge=90, le=365),
    window_days: int = Query(default=30, ge=7, le=90),
    risk_threshold: int = Query(default=60, ge=0, le=100),
    hit_threshold_percent: float = Query(default=3.0, gt=0, le=50),
    client: CoinGeckoClient = Depends(get_market_client),
) -> RiskBacktestResult:
    try:
        history_points = await client.get_history(coin_id, days)
        return backtest_risk(
            coin_id=coin_id,
            symbol=SUPPORTED_COINS[coin_id],
            history=history_points,
            window_days=window_days,
            risk_threshold=risk_threshold,
            hit_threshold_percent=hit_threshold_percent,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported coin or insufficient history: {coin_id}") from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
    if payload.email_enabled and not email_is_configured(settings):
        raise HTTPException(status_code=409, detail="管理员尚未完整配置邮件发送服务")
    if payload.email_enabled and not UserRepository(database).is_email_verified(user.id):
        raise HTTPException(status_code=403, detail="请先验证登录邮箱，再开启邮件通知")
    row = NotificationRepository(database, user.id).update(payload)
    return preference_response(row, settings)


@app.post("/api/notifications/test-email", response_model=NotificationTestResponse, tags=["notifications"])
async def send_test_email(
    user: UserRow = Depends(get_current_user),
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> NotificationTestResponse:
    if not email_is_configured(settings):
        raise HTTPException(status_code=409, detail="管理员尚未完整配置邮件发送服务")
    if not UserRepository(database).is_email_verified(user.id):
        raise HTTPException(status_code=403, detail="请先验证登录邮箱，再发送测试邮件")
    now = monotonic()
    last_sent = _last_test_email_sent.get(user.id)
    elapsed = now - last_sent if last_sent is not None else None
    if elapsed is not None and elapsed < 60:
        raise HTTPException(status_code=429, detail=f"请在 {int(60 - elapsed) + 1} 秒后再次测试")
    try:
        await NotificationService(database, settings).send_test_email(user.email)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"测试邮件发送失败：{str(exc)[:300]}") from exc
    _last_test_email_sent[user.id] = monotonic()
    return NotificationTestResponse(
        status="sent",
        recipient=user.email,
        provider=email_provider(settings),
        sent_at=datetime.now(UTC).isoformat(),
        message="测试邮件已发出，请检查收件箱和垃圾邮件文件夹。",
    )


static_directory = os.getenv("STATIC_DIR")
if static_directory:
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="web")
