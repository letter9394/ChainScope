export type RiskLevel = "low" | "medium" | "high";

export interface MarketCoin {
  id: string;
  symbol: string;
  name: string;
  image: string | null;
  current_price: number;
  market_cap: number | null;
  total_volume: number | null;
  price_change_percentage_24h: number | null;
  price_change_percentage_7d: number | null;
  last_updated: string | null;
  sparkline: number[];
}

export interface HistoryPoint {
  timestamp: number;
  price: number;
  volume: number | null;
}

export type CandleInterval = "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w";

export interface CandlePoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleSeries {
  asset_id: string;
  symbol: string;
  display_symbol: string;
  interval: CandleInterval;
  provider: string;
  is_proxy: boolean;
  proxy_notice: string | null;
  updated_at: string;
  candles: CandlePoint[];
}

export interface RiskMetric {
  key: string;
  label: string;
  value: number;
  display_value: string;
  contribution: number;
  explanation: string;
}

export interface DerivativesSnapshot {
  coin_id: string;
  symbol: string;
  available: boolean;
  funding_rate_percent: number | null;
  annualized_funding_percent: number | null;
  mark_price: number | null;
  next_funding_time: string | null;
  open_interest_usd: number | null;
  open_interest_change_5m_percent: number | null;
  long_short_ratio: number | null;
  long_account_percent: number | null;
  short_account_percent: number | null;
  fear_greed_value: number | null;
  fear_greed_label: string | null;
  updated_at: string;
  source: string;
}

export interface RiskAssessment {
  coin_id: string;
  symbol: string;
  score: number;
  level: RiskLevel;
  level_label: string;
  summary: string;
  metrics: RiskMetric[];
  sample_days: number;
  calculated_at: string;
  market_context: DerivativesSnapshot | null;
}

export interface RiskBacktestHorizon {
  horizon_days: number;
  samples: number;
  hit_count: number;
  hit_rate_percent: number;
  average_max_drawdown_percent: number;
  worst_max_drawdown_percent: number;
}

export interface RiskBacktestSignal {
  timestamp: number;
  score: number;
  price: number;
  future_drawdowns: Record<string, number>;
}

export interface RiskBacktestRegime {
  regime: "bull" | "bear" | "sideways";
  label: string;
  signal_count: number;
  hit_count: number;
  hit_rate_percent: number;
  average_max_drawdown_percent: number;
}

export interface RiskBacktestValidation {
  horizon_days: number;
  split_timestamp: number;
  training_points: number;
  holdout_points: number;
  training_signal_count: number;
  holdout_signal_count: number;
  training_hit_rate_percent: number;
  holdout_hit_rate_percent: number;
}

export interface RiskBacktestSensitivity {
  threshold: number;
  horizon_days: number;
  signal_count: number;
  hit_rate_percent: number;
  average_max_drawdown_percent: number;
}

export interface RiskBacktestQuality {
  horizon_days: number;
  evaluated_days: number;
  event_days: number;
  signal_count: number;
  true_positive_count: number;
  false_positive_count: number;
  false_negative_count: number;
  true_negative_count: number;
  baseline_hit_rate_percent: number;
  accuracy_percent: number;
  precision_percent: number;
  recall_percent: number;
  miss_rate_percent: number;
  lift: number;
}

export interface RiskBacktestWalkForwardFold {
  fold: number;
  selected_threshold: number;
  training_points: number;
  holdout_points: number;
  holdout_start: number;
  holdout_end: number;
  holdout_event_count: number;
  holdout_signal_count: number;
  baseline_hit_rate_percent: number;
  precision_percent: number;
  recall_percent: number;
  lift: number;
}

export interface RiskBacktestWalkForward {
  horizon_days: number;
  embargo_days: number;
  candidate_thresholds: number[];
  total_holdout_points: number;
  event_days: number;
  signal_count: number;
  baseline_hit_rate_percent: number;
  accuracy_percent: number;
  precision_percent: number;
  recall_percent: number;
  miss_rate_percent: number;
  lift: number;
  folds: RiskBacktestWalkForwardFold[];
}

export interface RiskFeatureImportance {
  key: string;
  label: string;
  coefficient: number;
  direction: "raises_risk" | "lowers_risk";
}

export interface RiskFeatureModelFold {
  fold: number;
  probability_threshold_percent: number;
  training_points: number;
  holdout_points: number;
  holdout_start: number;
  holdout_end: number;
  holdout_event_count: number;
  holdout_signal_count: number;
  baseline_hit_rate_percent: number;
  precision_percent: number;
  recall_percent: number;
  lift: number;
}

export interface RiskFeatureModelResult {
  status: "validated" | "insufficient_data";
  model_name: string;
  target: string;
  horizon_days: number;
  lookback_days: number;
  embargo_days: number;
  total_holdout_points: number;
  event_days: number;
  signal_count: number;
  baseline_hit_rate_percent: number;
  accuracy_percent: number;
  precision_percent: number;
  recall_percent: number;
  miss_rate_percent: number;
  lift: number;
  promoted: boolean;
  verdict: string;
  feature_importance: RiskFeatureImportance[];
  folds: RiskFeatureModelFold[];
}

export interface RiskLabelExperimentFold {
  fold: number;
  holdout_start: number;
  holdout_end: number;
  event_threshold_percent: number;
  probability_threshold_percent: number;
  training_points: number;
  holdout_points: number;
  holdout_event_count: number;
  holdout_signal_count: number;
  baseline_hit_rate_percent: number;
  precision_percent: number;
  recall_percent: number;
  lift: number;
  brier_score: number;
  brier_skill_score: number;
  calibration_error_percent: number;
}

export interface RiskConfidenceInterval {
  lower: number;
  upper: number;
  confidence_level_percent: number;
  method: string;
  resamples: number;
  block_days: number;
}

export interface RiskLabelExperimentResult {
  key: "fixed" | "volatility" | "quantile";
  label: string;
  target: string;
  status: "validated" | "insufficient_data";
  total_holdout_points: number;
  event_days: number;
  signal_count: number;
  baseline_hit_rate_percent: number;
  precision_percent: number;
  recall_percent: number;
  lift: number;
  brier_score: number;
  brier_skill_score: number;
  calibration_error_percent: number;
  precision_confidence_interval: RiskConfidenceInterval | null;
  lift_confidence_interval: RiskConfidenceInterval | null;
  brier_confidence_interval: RiskConfidenceInterval | null;
  folds: RiskLabelExperimentFold[];
}

export interface RiskLabelStudyResult {
  model_name: string;
  horizon_days: number;
  status: "validated" | "insufficient_data";
  recommended_key: "volatility" | "quantile" | null;
  recommended: boolean;
  verdict: string;
  experiments: RiskLabelExperimentResult[];
}

export interface RiskLabelHorizonReview {
  horizon_days: number;
  status: "validated" | "insufficient_data";
  selected_key: "fixed" | "volatility" | "quantile";
  selected_label: string;
  lift: number;
  lift_confidence_lower: number | null;
  brier_skill_score: number;
  passed: boolean;
  verdict: string;
}

export interface RiskLabelStabilityResult {
  model_name: string;
  required_horizons: number[];
  consistent_key: "volatility" | "quantile" | null;
  stable: boolean;
  verdict: string;
  horizons: RiskLabelHorizonReview[];
}

export interface RiskTemporalStabilityPeriod {
  period: number;
  holdout_start: number;
  holdout_end: number;
  holdout_points: number;
  event_days: number;
  signal_count: number;
  baseline_hit_rate_percent: number;
  precision_percent: number;
  lift: number;
  brier_skill_score: number;
  calibration_error_percent: number;
  passed: boolean;
}

export interface RiskTemporalStabilityResult {
  model_name: string;
  status: "stable" | "mixed" | "deteriorating" | "insufficient_data";
  selected_key: "fixed" | "volatility" | "quantile";
  selected_label: string;
  horizon_days: number;
  lift_change: number;
  brier_skill_change: number;
  event_rate_change_percent_points: number;
  verdict: string;
  periods: RiskTemporalStabilityPeriod[];
}

export interface RiskBacktestResult {
  coin_id: string;
  symbol: string;
  model_version: string;
  history_days: number;
  window_days: number;
  risk_threshold: number;
  hit_threshold_percent: number;
  evaluated_points: number;
  signal_count: number;
  sample_start: number;
  sample_end: number;
  horizons: RiskBacktestHorizon[];
  regimes: RiskBacktestRegime[];
  validation: RiskBacktestValidation;
  sensitivity: RiskBacktestSensitivity[];
  quality: RiskBacktestQuality;
  walk_forward: RiskBacktestWalkForward;
  feature_model: RiskFeatureModelResult;
  label_study: RiskLabelStudyResult;
  label_stability: RiskLabelStabilityResult;
  temporal_stability: RiskTemporalStabilityResult;
  recent_signals: RiskBacktestSignal[];
  methodology: string;
  calculated_at: string;
}

export interface RiskBacktestPortfolioAsset {
  coin_id: string;
  symbol: string;
  status: "validated" | "insufficient_data" | "unavailable";
  baseline_hit_rate_percent: number | null;
  precision_percent: number | null;
  recall_percent: number | null;
  lift: number | null;
  signal_count: number;
  passed: boolean;
  recommended_label: "volatility" | "quantile" | null;
  label_improved: boolean;
  stable_horizons: number;
}

export interface RiskBacktestPortfolioResult {
  model_name: string;
  target: string;
  required_passing_assets: number;
  passing_assets: number;
  available_assets: number;
  promoted: boolean;
  verdict: string;
  label_study_passing_assets: number;
  label_study_recommended: boolean;
  label_study_verdict: string;
  assets: RiskBacktestPortfolioAsset[];
  calculated_at: string;
}

export interface RiskDriftSnapshot {
  id: number;
  coin_id: string;
  symbol: string;
  status: "stable" | "mixed" | "deteriorating" | "insufficient_data";
  selected_key: "fixed" | "volatility" | "quantile";
  selected_label: string;
  horizon_days: number;
  lift_change: number;
  brier_skill_change: number;
  event_rate_change_percent_points: number;
  latest_lift: number;
  latest_brier_skill_score: number;
  observed_at: string;
}

export interface RiskDriftEvent {
  id: number;
  coin_id: string;
  symbol: string;
  previous_status: "stable" | "mixed" | "deteriorating" | "insufficient_data";
  current_status: "stable" | "mixed" | "deteriorating" | "insufficient_data";
  severity: "info" | "warning";
  title: string;
  message: string;
  created_at: string;
}

export interface RiskDriftAssetState {
  coin_id: string;
  symbol: string;
  current: RiskDriftSnapshot | null;
  history: RiskDriftSnapshot[];
}

export interface RiskDriftMonitorResult {
  model_name: string;
  status: "starting" | "ok" | "degraded" | "error" | "disabled";
  interval_seconds: number;
  last_checked_at: string | null;
  assets: RiskDriftAssetState[];
  events: RiskDriftEvent[];
}

export interface NewsArticle {
  id: string;
  title: string;
  url: string;
  source: string;
  published_at: string;
  image_url: string | null;
  summary: string;
  sentiment: "positive" | "neutral" | "negative";
  sentiment_label: string;
  related_symbols: string[];
  analysis_mode: "rules" | "ai";
}

export interface NewsResponse {
  articles: NewsArticle[];
  analysis_mode: "rules" | "ai";
  notice: string;
}

export interface NewsTranslation {
  title_zh: string;
  summary_zh: string;
  provider: string;
}

export interface WatchlistItem {
  coin_id: string;
  symbol: string;
  added_at: string;
}

export type AlertMetric = "risk_score" | "price_change_24h";
export type AlertOperator = "gte" | "lte";

export interface AlertRuleInput {
  coin_id: string;
  metric: AlertMetric;
  operator: AlertOperator;
  threshold: number;
}

export interface AlertRule extends AlertRuleInput {
  id: number;
  symbol: string;
  enabled: boolean;
  is_triggered: boolean;
  created_at: string;
  last_triggered_at: string | null;
}

export interface AlertEvent {
  id: number;
  rule_id: number;
  coin_id: string;
  symbol: string;
  metric: AlertMetric;
  operator: AlertOperator;
  threshold: number;
  observed_value: number;
  severity: "warning" | "critical";
  title: string;
  message: string;
  triggered_at: string;
  acknowledged_at: string | null;
}

export interface AlertEvaluationResponse {
  evaluated_rules: number;
  triggered_events: AlertEvent[];
  active_events: AlertEvent[];
}

export interface AuthUser {
  id: number;
  email: string;
  created_at: string;
  email_verified: boolean;
}

export interface PasswordResetRequestResult {
  message: string;
}

export interface AuthMessageResult {
  message: string;
}

export interface NotificationSettings {
  in_app_enabled: boolean;
  email_enabled: boolean;
  drift_email_enabled: boolean;
  email_available: boolean;
  email_provider: string;
  email_sender: string | null;
  schedule_seconds: number;
  schedule_mode: string;
}

export interface DriftEmailDelivery {
  event_id: number;
  coin_id: string;
  symbol: string;
  title: string;
  status: "sent" | "delivered" | "bounced" | "deferred" | "blocked" | "failed" | "suppressed";
  attempted_at: string;
  provider_event_at?: string | null;
}

export interface NotificationTestResult {
  status: "sent";
  recipient: string;
  provider: string;
  sent_at: string;
  message: string;
}
