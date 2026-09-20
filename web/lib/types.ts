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

export interface RiskMetric {
  key: string;
  label: string;
  value: number;
  display_value: string;
  contribution: number;
  explanation: string;
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
