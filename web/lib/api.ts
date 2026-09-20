import type { HistoryPoint, MarketCoin, NewsResponse, RiskAssessment, WatchlistItem } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function apiRequest<T>(
  path: string,
  signal?: AbortSignal,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
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

export const getWatchlist = (signal?: AbortSignal) =>
  apiRequest<WatchlistItem[]>("/api/watchlist", signal);

export const addToWatchlist = (coinId: string) =>
  apiRequest<WatchlistItem>(`/api/watchlist/${coinId}`, undefined, { method: "POST" });

export async function removeFromWatchlist(coinId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/watchlist/${coinId}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    throw new Error(`删除自选失败（${response.status}）`);
  }
}
