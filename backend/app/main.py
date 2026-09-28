import asyncio
import hashlib
import hmac
import logging
import os
import re
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from functools import lru_cache
from time import monotonic, perf_counter
from urllib.parse import quote, urlsplit
from uuid import uuid4
from weakref import WeakKeyDictionary

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.database import Database, UserRow
from app.migrations import upgrade_database
from app.models import (
    AlertEvaluationResponse, AlertEvent, AlertRule, AlertRuleCreate, AuthCredentials,
    AuthMessageResponse, AuthUser, CandleSeries, CsrfTokenResponse, DerivativesSnapshot,
    EmailVerificationConfirm, HealthCheck, HealthResponse, HistoryPoint, MarketCoin,
    NewsResponse, NewsTranslationRequest, NewsTranslationResponse,
    NotificationSettingsResponse, NotificationSettingsUpdate, NotificationTestResponse,
    PasswordResetConfirm, PasswordResetRequest, PasswordResetRequestResponse, RiskAssessment,
    RiskBacktestPortfolioAsset, RiskBacktestPortfolioResult, RiskBacktestResult, WatchlistItem,
    SchedulerHealth,
)
from app.observability import (
    PROCESS_STARTED_MONOTONIC, configure_logging, scheduler_runtime, utc_iso,
)
from app.services.alerts import AlertRepository, evaluate_alert_rules
from app.services.auth import (
    UserRepository, create_email_verification_token, create_password_reset_token,
    create_session_token, decode_email_verification_token, decode_password_reset_token,
    decode_session_token, user_model, verify_password,
)
from app.services.cache import cache
from app.services.csrf import create_csrf_token, validate_csrf_token
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
request_logger = logging.getLogger("chainscope.http")
service_logger = logging.getLogger("chainscope.service")
_request_id_pattern = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_unsafe_methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_risk_backtest_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()


def _risk_backtest_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _risk_backtest_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _risk_backtest_locks[loop] = lock
    return lock


@lru_cache
def database_for_url(url: str) -> Database:
    upgrade_database(url)
    return Database(url, initialize_schema=False)


def get_database(settings: Settings = Depends(get_settings)) -> Database:
    return database_for_url(settings.resolved_database_url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_logs=settings.log_json if settings.log_json is not None else settings.chain_scope_env == "production",
    )
    scheduler_runtime.reset()
    database = database_for_url(settings.resolved_database_url)
    scheduler_task = None
    backtest_prewarm_task = None
    if settings.background_alerts_enabled:
        scheduler_task = asyncio.create_task(run_alert_scheduler(database, settings))
    if settings.risk_backtest_prewarm_enabled:
        backtest_prewarm_task = asyncio.create_task(_prewarm_default_risk_backtest(settings))
    service_logger.info(
        "service_started",
        extra={
            "environment": settings.chain_scope_env,
            "database": "postgresql" if settings.resolved_database_url.startswith("postgresql") else "sqlite",
            "background_alerts": settings.background_alerts_enabled,
            "risk_backtest_prewarm": settings.risk_backtest_prewarm_enabled,
        },
    )
    yield
    for task in (scheduler_task, backtest_prewarm_task):
        if task is None:
            continue
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    service_logger.info("service_stopped")


app = FastAPI(
    title="ChainScope API",
    description="Market data, accounts, and explainable cryptocurrency risk alerts.",
    version="1.0.0",
    lifespan=lifespan,
)

def _settings_for_request() -> Settings:
    override = app.dependency_overrides.get(get_settings)
    return override() if override is not None else get_settings()


def _normalized_origin(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _allowed_origins(request: Request, settings: Settings) -> set[str]:
    origins = {
        origin
        for origin in (
            _normalized_origin(settings.public_app_url),
            _normalized_origin(str(request.base_url)),
        )
        if origin is not None
    }
    if settings.chain_scope_env != "production":
        origins.update(
            {
                "http://localhost:3100",
                "http://127.0.0.1:3100",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            }
        )
    return origins


def _csrf_failure_reason(request: Request, settings: Settings) -> str | None:
    if (
        not settings.csrf_protection_enabled
        or request.method.upper() not in _unsafe_methods
        or not request.url.path.startswith("/api/")
    ):
        return None

    allowed_origins = _allowed_origins(request, settings)
    origin_header = request.headers.get("origin")
    referer_header = request.headers.get("referer")
    supplied_origin = _normalized_origin(origin_header)
    if origin_header and supplied_origin not in allowed_origins:
        return "origin"
    if not origin_header and referer_header:
        supplied_referer = _normalized_origin(referer_header)
        if supplied_referer not in allowed_origins:
            return "referer"
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return "fetch-site"

    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token:
        return "missing-token"
    if not hmac.compare_digest(cookie_token, header_token):
        return "token-mismatch"
    if not validate_csrf_token(
        cookie_token,
        settings.session_secret,
        settings.csrf_max_age_seconds,
    ):
        return "invalid-token"
    return None


@app.middleware("http")
async def request_observability(request: Request, call_next):
    supplied_request_id = request.headers.get("x-request-id", "")
    request_id = (
        supplied_request_id
        if _request_id_pattern.fullmatch(supplied_request_id)
        else uuid4().hex
    )
    started_at = perf_counter()
    csrf_failure = _csrf_failure_reason(request, _settings_for_request())
    if csrf_failure is not None:
        response = JSONResponse(
            status_code=403,
            content={"detail": "CSRF validation failed"},
            headers={"X-CSRF-Error": "1"},
        )
        request_logger.warning(
            "csrf_request_rejected",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "csrf_reason": csrf_failure,
            },
        )
    else:
        try:
            response = await call_next(request)
        except Exception as exc:
            request_logger.error(
                "http_request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                    "error_type": type(exc).__name__,
                },
            )
            raise
    response.headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/api/") or response.status_code >= 400:
        request_logger.info(
            "http_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
    return response


# Added after the function middleware so CORS remains the outermost layer and
# exposes CSRF refresh signals even when a request is rejected before routing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Error", "X-Request-ID"],
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
async def health(
    response: Response,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> HealthResponse:
    database_started_at = perf_counter()
    database_status = "ok"
    database_detail = None
    try:
        await asyncio.to_thread(database.ping)
    except Exception as exc:
        database_status = "error"
        database_detail = f"Database check failed ({type(exc).__name__})"
        service_logger.error(
            "health_database_check_failed",
            extra={"error_type": type(exc).__name__},
        )
    database_check = HealthCheck(
        status=database_status,
        latency_ms=round((perf_counter() - database_started_at) * 1000, 2),
        detail=database_detail,
    )
    scheduler_check = SchedulerHealth(
        **scheduler_runtime.snapshot(
            enabled=settings.background_alerts_enabled,
            interval_seconds=max(15, settings.alert_check_seconds),
        )
    )
    email_configured = email_is_configured(settings)
    email_check = HealthCheck(
        status="ok" if email_configured else "unconfigured",
        detail=email_provider(settings) if email_configured else "Email notifications are not configured",
    )
    overall_status = (
        "degraded"
        if database_check.status == "error" or scheduler_check.status in {"error", "degraded"}
        else "ok"
    )
    if database_check.status == "error":
        response.status_code = 503
    return HealthResponse(
        status=overall_status,
        checked_at=utc_iso(),
        uptime_seconds=round(monotonic() - PROCESS_STARTED_MONOTONIC, 2),
        version=(os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "local")[:12],
        environment=settings.chain_scope_env,
        market_provider="Binance Spot/Futures/Klines + CoinGecko + Gold API + Alternative.me",
        database="postgresql" if settings.resolved_database_url.startswith("postgresql") else "sqlite",
        background_alerts=settings.background_alerts_enabled,
        checks={
            "database": database_check,
            "scheduler": scheduler_check,
            "email": email_check,
        },
    )


@app.get("/api/assets/{asset_id}/candles", response_model=CandleSeries, tags=["market"])
async def asset_candles(
    asset_id: str,
    interval: str = Query(default="15m"),
    limit: int = Query(default=300, ge=2, le=1_000),
    source: str = Query(default="auto", pattern="^(auto|exact|proxy)$"),
    client: CoinGeckoClient = Depends(get_market_client),
) -> CandleSeries:
    try:
        return await client.get_candles(asset_id, interval, limit, source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/auth/csrf", response_model=CsrfTokenResponse, tags=["auth"])
async def csrf_token(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> CsrfTokenResponse:
    token = request.cookies.get(settings.csrf_cookie_name)
    if not validate_csrf_token(
        token,
        settings.session_secret,
        settings.csrf_max_age_seconds,
    ):
        token = create_csrf_token(settings.session_secret)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.csrf_max_age_seconds,
        httponly=False,
        secure=settings.chain_scope_env == "production",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return CsrfTokenResponse(csrf_token=token)


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


def _risk_backtest_cache_key(
    coin_id: str,
    days: int,
    window_days: int,
    risk_threshold: int,
    hit_threshold_percent: float,
) -> str:
    return (
        f"risk-backtest:v5:{coin_id}:{days}:{window_days}:"
        f"{risk_threshold}:{hit_threshold_percent:g}"
    )


async def _get_or_compute_risk_backtest(
    *,
    coin_id: str,
    days: int,
    window_days: int,
    risk_threshold: int,
    hit_threshold_percent: float,
    client: CoinGeckoClient,
    settings: Settings,
) -> tuple[RiskBacktestResult, bool]:
    cache_key = _risk_backtest_cache_key(
        coin_id,
        days,
        window_days,
        risk_threshold,
        hit_threshold_percent,
    )
    cached = cache.get(cache_key)
    if isinstance(cached, RiskBacktestResult):
        return cached, True

    async with _risk_backtest_lock():
        cached = cache.get(cache_key)
        if isinstance(cached, RiskBacktestResult):
            return cached, True

        history_points = await client.get_history(coin_id, days)
        result = await asyncio.to_thread(
            backtest_risk,
            coin_id=coin_id,
            symbol=SUPPORTED_COINS[coin_id],
            history=history_points,
            window_days=window_days,
            risk_threshold=risk_threshold,
            hit_threshold_percent=hit_threshold_percent,
        )
        cache.set(cache_key, result, settings.risk_backtest_cache_seconds)
        return result, False


async def _prewarm_default_risk_backtest(settings: Settings) -> None:
    started_at = perf_counter()
    service_logger.info("risk_backtest_prewarm_started")
    market_client = CoinGeckoClient(settings)
    warmed_assets: list[str] = []
    failed_assets: list[str] = []
    for coin_id in SUPPORTED_COINS:
        try:
            await _get_or_compute_risk_backtest(
                coin_id=coin_id,
                days=1095,
                window_days=30,
                risk_threshold=60,
                hit_threshold_percent=3.0,
                client=market_client,
                settings=settings,
            )
            warmed_assets.append(coin_id)
        except Exception as exc:
            failed_assets.append(coin_id)
            service_logger.warning(
                "risk_backtest_prewarm_asset_failed",
                extra={"coin_id": coin_id, "error_type": type(exc).__name__},
            )
    service_logger.info(
        "risk_backtest_prewarm_completed",
        extra={
            "warmed_assets": warmed_assets,
            "failed_assets": failed_assets,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        },
    )


@app.get(
    "/api/risk/backtests",
    response_model=RiskBacktestPortfolioResult,
    tags=["risk"],
)
async def risk_backtest_portfolio(
    response: Response,
    days: int = Query(default=1095, ge=90, le=1825),
    window_days: int = Query(default=30, ge=7, le=90),
    risk_threshold: int = Query(default=60, ge=0, le=100),
    hit_threshold_percent: float = Query(default=3.0, gt=0, le=50),
    client: CoinGeckoClient = Depends(get_market_client),
    settings: Settings = Depends(get_settings),
) -> RiskBacktestPortfolioResult:
    evaluations = await asyncio.gather(
        *(
            _get_or_compute_risk_backtest(
                coin_id=coin_id,
                days=days,
                window_days=window_days,
                risk_threshold=risk_threshold,
                hit_threshold_percent=hit_threshold_percent,
                client=client,
                settings=settings,
            )
            for coin_id in SUPPORTED_COINS
        ),
        return_exceptions=True,
    )
    assets: list[RiskBacktestPortfolioAsset] = []
    all_cache_hits = True
    for (coin_id, symbol), evaluation in zip(SUPPORTED_COINS.items(), evaluations, strict=True):
        if isinstance(evaluation, BaseException):
            all_cache_hits = False
            service_logger.warning(
                "risk_backtest_portfolio_asset_failed",
                extra={"coin_id": coin_id, "error_type": type(evaluation).__name__},
            )
            assets.append(
                RiskBacktestPortfolioAsset(
                    coin_id=coin_id,
                    symbol=symbol,
                    status="unavailable",
                )
            )
            continue
        result, cache_hit = evaluation
        all_cache_hits = all_cache_hits and cache_hit
        feature_model = result.feature_model
        label_study = result.label_study
        assets.append(
            RiskBacktestPortfolioAsset(
                coin_id=coin_id,
                symbol=symbol,
                status=feature_model.status,
                baseline_hit_rate_percent=feature_model.baseline_hit_rate_percent,
                precision_percent=feature_model.precision_percent,
                recall_percent=feature_model.recall_percent,
                lift=feature_model.lift,
                signal_count=feature_model.signal_count,
                passed=feature_model.promoted,
                recommended_label=label_study.recommended_key,
                label_improved=label_study.recommended,
            )
        )

    required_passing_assets = 2
    passing_assets = sum(asset.passed for asset in assets)
    available_assets = sum(asset.status == "validated" for asset in assets)
    promoted = passing_assets >= required_passing_assets
    label_study_passing_assets = sum(asset.label_improved for asset in assets)
    label_study_recommended = label_study_passing_assets >= required_passing_assets
    response.headers["X-ChainScope-Cache"] = "hit" if all_cache_hits else "miss"
    verdict = (
        f"跨资产门槛通过：{passing_assets} 个资产通过完整留出期验证，可进入影子运行。"
        if promoted
        else f"跨资产门槛未通过：仅 {passing_assets} 个资产达标，至少需要 {required_passing_assets} 个。"
    )
    label_study_verdict = (
        f"标签替换门槛通过：{label_study_passing_assets} 个资产独立改善，可进入影子运行。"
        if label_study_recommended
        else (
            f"标签替换门槛未通过：仅 {label_study_passing_assets} 个资产独立改善，"
            f"至少需要 {required_passing_assets} 个；线上标签保持不变。"
        )
    )
    return RiskBacktestPortfolioResult(
        model_name="v0.4 标准化逻辑回归实验",
        target=f"未来7日最大跌幅 ≥ {hit_threshold_percent:g}%",
        required_passing_assets=required_passing_assets,
        passing_assets=passing_assets,
        available_assets=available_assets,
        promoted=promoted,
        verdict=verdict,
        label_study_passing_assets=label_study_passing_assets,
        label_study_recommended=label_study_recommended,
        label_study_verdict=label_study_verdict,
        assets=assets,
        calculated_at=utc_iso(),
    )


@app.get(
    "/api/coins/{coin_id}/risk/backtest",
    response_model=RiskBacktestResult,
    tags=["risk"],
)
async def risk_backtest(
    coin_id: str,
    response: Response,
    days: int = Query(default=1095, ge=90, le=1825),
    window_days: int = Query(default=30, ge=7, le=90),
    risk_threshold: int = Query(default=60, ge=0, le=100),
    hit_threshold_percent: float = Query(default=3.0, gt=0, le=50),
    client: CoinGeckoClient = Depends(get_market_client),
    settings: Settings = Depends(get_settings),
) -> RiskBacktestResult:
    try:
        result, cache_hit = await _get_or_compute_risk_backtest(
            coin_id=coin_id,
            days=days,
            window_days=window_days,
            risk_threshold=risk_threshold,
            hit_threshold_percent=hit_threshold_percent,
            client=client,
            settings=settings,
        )
        response.headers["X-ChainScope-Cache"] = "hit" if cache_hit else "miss"
        return result
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
