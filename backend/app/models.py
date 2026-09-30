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


class CandlePoint(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleSeries(BaseModel):
    asset_id: str
    symbol: str
    display_symbol: str
    interval: str
    provider: str
    is_proxy: bool = False
    proxy_notice: str | None = None
    updated_at: str
    candles: list[CandlePoint]


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


class RiskBacktestHorizon(BaseModel):
    horizon_days: int
    samples: int
    hit_count: int
    hit_rate_percent: float
    average_max_drawdown_percent: float
    worst_max_drawdown_percent: float


class RiskBacktestSignal(BaseModel):
    timestamp: int
    score: int
    price: float
    future_drawdowns: dict[str, float]


class RiskBacktestRegime(BaseModel):
    regime: Literal["bull", "bear", "sideways"]
    label: str
    signal_count: int
    hit_count: int
    hit_rate_percent: float
    average_max_drawdown_percent: float


class RiskBacktestValidation(BaseModel):
    horizon_days: int
    split_timestamp: int
    training_points: int
    holdout_points: int
    training_signal_count: int
    holdout_signal_count: int
    training_hit_rate_percent: float
    holdout_hit_rate_percent: float


class RiskBacktestSensitivity(BaseModel):
    threshold: int
    horizon_days: int
    signal_count: int
    hit_rate_percent: float
    average_max_drawdown_percent: float


class RiskBacktestQuality(BaseModel):
    horizon_days: int
    evaluated_days: int
    event_days: int
    signal_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    true_negative_count: int
    baseline_hit_rate_percent: float
    accuracy_percent: float
    precision_percent: float
    recall_percent: float
    miss_rate_percent: float
    lift: float


class RiskBacktestWalkForwardFold(BaseModel):
    fold: int
    selected_threshold: int
    training_points: int
    holdout_points: int
    holdout_start: int
    holdout_end: int
    holdout_event_count: int
    holdout_signal_count: int
    baseline_hit_rate_percent: float
    precision_percent: float
    recall_percent: float
    lift: float


class RiskBacktestWalkForward(BaseModel):
    horizon_days: int
    embargo_days: int
    candidate_thresholds: list[int]
    total_holdout_points: int
    event_days: int
    signal_count: int
    baseline_hit_rate_percent: float
    accuracy_percent: float
    precision_percent: float
    recall_percent: float
    miss_rate_percent: float
    lift: float
    folds: list[RiskBacktestWalkForwardFold]


class RiskFeatureImportance(BaseModel):
    key: str
    label: str
    coefficient: float
    direction: Literal["raises_risk", "lowers_risk"]


class RiskFeatureModelFold(BaseModel):
    fold: int
    probability_threshold_percent: float
    training_points: int
    holdout_points: int
    holdout_start: int
    holdout_end: int
    holdout_event_count: int
    holdout_signal_count: int
    baseline_hit_rate_percent: float
    precision_percent: float
    recall_percent: float
    lift: float


class RiskFeatureModelResult(BaseModel):
    status: Literal["validated", "insufficient_data"]
    model_name: str
    target: str
    horizon_days: int
    lookback_days: int
    embargo_days: int
    total_holdout_points: int
    event_days: int
    signal_count: int
    baseline_hit_rate_percent: float
    accuracy_percent: float
    precision_percent: float
    recall_percent: float
    miss_rate_percent: float
    lift: float
    promoted: bool
    verdict: str
    feature_importance: list[RiskFeatureImportance]
    folds: list[RiskFeatureModelFold]


class RiskLabelExperimentFold(BaseModel):
    fold: int
    holdout_start: int
    holdout_end: int
    event_threshold_percent: float
    probability_threshold_percent: float
    training_points: int
    holdout_points: int
    holdout_event_count: int
    holdout_signal_count: int
    baseline_hit_rate_percent: float
    precision_percent: float
    recall_percent: float
    lift: float
    brier_score: float
    brier_skill_score: float
    calibration_error_percent: float


class RiskConfidenceInterval(BaseModel):
    lower: float
    upper: float
    confidence_level_percent: float = 95.0
    method: str
    resamples: int
    block_days: int


class RiskLabelExperimentResult(BaseModel):
    key: Literal["fixed", "volatility", "quantile"]
    label: str
    target: str
    status: Literal["validated", "insufficient_data"]
    total_holdout_points: int
    event_days: int
    signal_count: int
    baseline_hit_rate_percent: float
    precision_percent: float
    recall_percent: float
    lift: float
    brier_score: float
    brier_skill_score: float
    calibration_error_percent: float
    precision_confidence_interval: RiskConfidenceInterval | None = None
    lift_confidence_interval: RiskConfidenceInterval | None = None
    brier_confidence_interval: RiskConfidenceInterval | None = None
    folds: list[RiskLabelExperimentFold]


class RiskLabelStudyResult(BaseModel):
    model_name: str
    horizon_days: int
    status: Literal["validated", "insufficient_data"]
    recommended_key: Literal["volatility", "quantile"] | None = None
    recommended: bool
    verdict: str
    experiments: list[RiskLabelExperimentResult]


class RiskLabelHorizonReview(BaseModel):
    horizon_days: int
    status: Literal["validated", "insufficient_data"]
    selected_key: Literal["fixed", "volatility", "quantile"]
    selected_label: str
    lift: float
    lift_confidence_lower: float | None = None
    brier_skill_score: float
    passed: bool
    verdict: str


class RiskLabelStabilityResult(BaseModel):
    model_name: str
    required_horizons: list[int]
    consistent_key: Literal["volatility", "quantile"] | None = None
    stable: bool
    verdict: str
    horizons: list[RiskLabelHorizonReview]


class RiskTemporalStabilityPeriod(BaseModel):
    period: int
    holdout_start: int
    holdout_end: int
    holdout_points: int
    event_days: int
    signal_count: int
    baseline_hit_rate_percent: float
    precision_percent: float
    lift: float
    brier_skill_score: float
    calibration_error_percent: float
    passed: bool


class RiskTemporalStabilityResult(BaseModel):
    model_name: str
    status: Literal["stable", "mixed", "deteriorating", "insufficient_data"]
    selected_key: Literal["fixed", "volatility", "quantile"]
    selected_label: str
    horizon_days: int
    lift_change: float
    brier_skill_change: float
    event_rate_change_percent_points: float
    verdict: str
    periods: list[RiskTemporalStabilityPeriod]


class RiskBacktestResult(BaseModel):
    coin_id: str
    symbol: str
    model_version: str
    history_days: int
    window_days: int
    risk_threshold: int
    hit_threshold_percent: float
    evaluated_points: int
    signal_count: int
    sample_start: int
    sample_end: int
    horizons: list[RiskBacktestHorizon]
    regimes: list[RiskBacktestRegime]
    validation: RiskBacktestValidation
    sensitivity: list[RiskBacktestSensitivity]
    quality: RiskBacktestQuality
    walk_forward: RiskBacktestWalkForward
    feature_model: RiskFeatureModelResult
    label_study: RiskLabelStudyResult
    label_stability: RiskLabelStabilityResult
    temporal_stability: RiskTemporalStabilityResult
    recent_signals: list[RiskBacktestSignal]
    methodology: str
    calculated_at: str


class RiskBacktestPortfolioAsset(BaseModel):
    coin_id: str
    symbol: str
    status: Literal["validated", "insufficient_data", "unavailable"]
    baseline_hit_rate_percent: float | None = None
    precision_percent: float | None = None
    recall_percent: float | None = None
    lift: float | None = None
    signal_count: int = 0
    passed: bool = False
    recommended_label: Literal["volatility", "quantile"] | None = None
    label_improved: bool = False
    stable_horizons: int = 0


class RiskBacktestPortfolioResult(BaseModel):
    model_name: str
    target: str
    required_passing_assets: int
    passing_assets: int
    available_assets: int
    promoted: bool
    verdict: str
    label_study_passing_assets: int
    label_study_recommended: bool
    label_study_verdict: str
    assets: list[RiskBacktestPortfolioAsset]
    calculated_at: str


class RiskDriftSnapshot(BaseModel):
    id: int
    coin_id: str
    symbol: str
    status: Literal["stable", "mixed", "deteriorating", "insufficient_data"]
    selected_key: Literal["fixed", "volatility", "quantile"]
    selected_label: str
    horizon_days: int
    lift_change: float
    brier_skill_change: float
    event_rate_change_percent_points: float
    latest_lift: float
    latest_brier_skill_score: float
    observed_at: str


class RiskDriftEvent(BaseModel):
    id: int
    coin_id: str
    symbol: str
    previous_status: Literal["stable", "mixed", "deteriorating", "insufficient_data"]
    current_status: Literal["stable", "mixed", "deteriorating", "insufficient_data"]
    severity: Literal["info", "warning"]
    title: str
    message: str
    created_at: str


class RiskDriftAssetState(BaseModel):
    coin_id: str
    symbol: str
    current: RiskDriftSnapshot | None = None
    history: list[RiskDriftSnapshot] = Field(default_factory=list)


class RiskDriftMonitorResponse(BaseModel):
    model_name: str
    status: Literal["starting", "ok", "degraded", "error", "disabled"]
    interval_seconds: int
    last_checked_at: str | None = None
    assets: list[RiskDriftAssetState]
    events: list[RiskDriftEvent]


class HealthCheck(BaseModel):
    status: Literal["ok", "starting", "degraded", "disabled", "unconfigured", "error"]
    latency_ms: float | None = None
    detail: str | None = None


class SchedulerHealth(HealthCheck):
    interval_seconds: int
    running: bool = False
    last_started_at: str | None = None
    last_completed_at: str | None = None
    last_error_at: str | None = None
    last_error_type: str | None = None
    last_duration_ms: float | None = None
    last_evaluated_users: int = 0
    last_triggered_events: int = 0
    last_failed_users: int = 0


class RiskDriftHealth(HealthCheck):
    interval_seconds: int
    running: bool = False
    last_started_at: str | None = None
    last_completed_at: str | None = None
    last_error_at: str | None = None
    last_error_type: str | None = None
    last_duration_ms: float | None = None
    last_evaluated_assets: int = 0
    last_transition_events: int = 0
    last_failed_assets: int = 0


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checked_at: str
    uptime_seconds: float
    version: str
    environment: str
    market_provider: str
    database: str = "sqlite"
    background_alerts: bool = False
    checks: dict[str, HealthCheck | SchedulerHealth | RiskDriftHealth] = Field(default_factory=dict)


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
    email_verified: bool


class EmailVerificationConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=2048)


class AuthMessageResponse(BaseModel):
    message: str


class CsrfTokenResponse(BaseModel):
    csrf_token: str


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[1]:
            raise ValueError("请输入有效的邮箱地址")
        return normalized


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=2048)
    password: str = Field(min_length=8, max_length=128)


class PasswordResetRequestResponse(BaseModel):
    message: str


class NotificationSettingsUpdate(BaseModel):
    email_enabled: bool = False
    drift_email_enabled: bool = False


class NotificationSettingsResponse(NotificationSettingsUpdate):
    in_app_enabled: bool = True
    email_available: bool
    email_provider: str
    email_sender: str | None = None
    schedule_seconds: int
    schedule_mode: str


class NotificationTestResponse(BaseModel):
    status: Literal["sent"]
    recipient: str
    provider: str
    sent_at: str
    message: str
