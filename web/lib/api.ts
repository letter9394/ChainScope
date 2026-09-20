import type {
  AlertEvaluationResponse,
  AlertEvent,
  AlertRule,
  AlertRuleInput,
  HistoryPoint,
  MarketCoin,
  NewsResponse,
  NewsTranslation,
  RiskAssessment,
  WatchlistItem,
} from "./types";

const CONFIGURED_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

function apiBaseUrl(): string {
  if (CONFIGURED_API_BASE_URL) return CONFIGURED_API_BASE_URL;
  if (
    typeof window !== "undefined" &&
    ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
    window.location.port === "3100"
  ) {
    return `http://${window.location.hostname}:8000`;
  }
  return "";
}

async function apiRequest<T>(
  path: string,
  signal?: AbortSignal,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // The status code is still useful when the body is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const getMarkets = (signal?: AbortSignal) =>
  apiRequest<MarketCoin[]>("/api/markets", signal);

export const getHistory = (coinId: string, days = 30, signal?: AbortSignal) =>
  apiRequest<HistoryPoint[]>(`/api/coins/${coinId}/history?days=${days}`, signal);

export const getRisk = (coinId: string, days = 30, signal?: AbortSignal) =>
  apiRequest<RiskAssessment>(`/api/coins/${coinId}/risk?days=${days}`, signal);

export const getNews = (coinId: string, limit = 6, signal?: AbortSignal) =>
  apiRequest<NewsResponse>(`/api/news?coin_id=${coinId}&limit=${limit}`, signal);

export const translateNews = (title: string, summary: string) =>
  apiRequest<NewsTranslation>("/api/news/translate", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, summary }),
  });

export const getWatchlist = (signal?: AbortSignal) =>
  apiRequest<WatchlistItem[]>("/api/watchlist", signal);

export const addToWatchlist = (coinId: string) =>
  apiRequest<WatchlistItem>(`/api/watchlist/${coinId}`, undefined, { method: "POST" });

export async function removeFromWatchlist(coinId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl()}/api/watchlist/${coinId}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    throw new Error(`删除自选失败（${response.status}）`);
  }
}

export const getAlertRules = (signal?: AbortSignal) =>
  apiRequest<AlertRule[]>("/api/alerts/rules", signal);

export const createAlertRule = (input: AlertRuleInput) =>
  apiRequest<AlertRule>("/api/alerts/rules", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

export async function deleteAlertRule(ruleId: number): Promise<void> {
  const response = await fetch(`${apiBaseUrl()}/api/alerts/rules/${ruleId}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    throw new Error(`删除预警规则失败（${response.status}）`);
  }
}

export const getAlertEvents = (signal?: AbortSignal) =>
  apiRequest<AlertEvent[]>("/api/alerts/events?limit=30", signal);

export const acknowledgeAlertEvent = (eventId: number) =>
  apiRequest<AlertEvent>(`/api/alerts/events/${eventId}/acknowledge`, undefined, {
    method: "POST",
  });

export const evaluateAlerts = () =>
  apiRequest<AlertEvaluationResponse>("/api/alerts/evaluate", undefined, {
    method: "POST",
  });
