from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MarketCoin(BaseModel):
    id: str
    symbol: str
    name: str
    image: str | None = None
    current_price: float
    market_cap: float | None = None
    total_volume: float | None = None
    price_change_percentage_24h: float | None = None
    price_change_percentage_7d: float | None = None
    last_updated: str | None = None
    sparkline: list[float] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    timestamp: int
    price: float
    volume: float | None = None


class RiskMetric(BaseModel):
    key: str
    label: str
    value: float
    display_value: str
    contribution: int
    explanation: str


class DerivativesSnapshot(BaseModel):
    coin_id: str
    symbol: str
    available: bool
    funding_rate_percent: float | None = None
    annualized_funding_percent: float | None = None
    mark_price: float | None = None
    next_funding_time: str | None = None
    open_interest_usd: float | None = None
    open_interest_change_5m_percent: float | None = None
    long_short_ratio: float | None = None
    long_account_percent: float | None = None
    short_account_percent: float | None = None
    fear_greed_value: int | None = None
    fear_greed_label: str | None = None
    updated_at: str
    source: str


class RiskAssessment(BaseModel):
    coin_id: str
    symbol: str
    score: int = Field(ge=0, le=100)
    level: Literal["low", "medium", "high"]
    level_label: str
    summary: str
    metrics: list[RiskMetric]
    sample_days: int
    calculated_at: str
    market_context: DerivativesSnapshot | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    market_provider: str
    database: str = "sqlite"
    background_alerts: bool = False


class NewsArticle(BaseModel):
    id: str
    title: str
    url: str
    source: str
    published_at: str
    image_url: str | None = None
    summary: str
    sentiment: Literal["positive", "neutral", "negative"]
    sentiment_label: str
    related_symbols: list[str] = Field(default_factory=list)
    analysis_mode: Literal["rules", "ai"]


class NewsResponse(BaseModel):
    articles: list[NewsArticle]
    analysis_mode: Literal["rules", "ai"]
    notice: str


class NewsTranslationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=500)


class NewsTranslationResponse(BaseModel):
    title_zh: str
    summary_zh: str
    provider: str


class WatchlistItem(BaseModel):
    coin_id: str
    symbol: str
    added_at: str


AlertMetric = Literal["risk_score", "price_change_24h"]
AlertOperator = Literal["gte", "lte"]


class AlertRuleCreate(BaseModel):
    coin_id: str
    metric: AlertMetric
    operator: AlertOperator
    threshold: float = Field(ge=-100, le=100)


class AlertRule(AlertRuleCreate):
    id: int
    symbol: str
    enabled: bool
    is_triggered: bool
    created_at: str
    last_triggered_at: str | None = None


class AlertEvent(BaseModel):
    id: int
    rule_id: int
    coin_id: str
    symbol: str
    metric: AlertMetric
    operator: AlertOperator
    threshold: float
    observed_value: float
    severity: Literal["warning", "critical"]
    title: str
    message: str
    triggered_at: str
    acknowledged_at: str | None = None


class AlertEvaluationResponse(BaseModel):
    evaluated_rules: int
    triggered_events: list[AlertEvent]
    active_events: list[AlertEvent]


class AuthCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[1]:
            raise ValueError("请输入有效的邮箱地址")
        return normalized


class AuthUser(BaseModel):
    id: int
    email: str
    created_at: str


class NotificationSettingsUpdate(BaseModel):
    email_enabled: bool = False
    telegram_enabled: bool = False
    telegram_chat_id: str | None = Field(default=None, max_length=128)


class NotificationSettingsResponse(NotificationSettingsUpdate):
    in_app_enabled: bool = True
    email_available: bool
    telegram_available: bool
    schedule_seconds: int
    schedule_mode: str
