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
  recent_signals: RiskBacktestSignal[];
  methodology: string;
  calculated_at: string;
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
}

export interface PasswordResetRequestResult {
  message: string;
}

export interface NotificationSettings {
  in_app_enabled: boolean;
  email_enabled: boolean;
  email_available: boolean;
  email_provider: string;
  email_sender: string | null;
  schedule_seconds: number;
  schedule_mode: string;
}

export interface NotificationTestResult {
  status: "sent";
  recipient: string;
  provider: string;
  sent_at: string;
  message: string;
}
