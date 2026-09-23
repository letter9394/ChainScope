import type {
  AlertEvaluationResponse,
  AlertEvent,
  AlertRule,
  AlertRuleInput,
  AuthUser,
  HistoryPoint,
  MarketCoin,
  NewsResponse,
  NewsTranslation,
  NotificationSettings,
  NotificationTestResult,
  PasswordResetRequestResult,
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
    credentials: "include",
  });

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
      if (typeof body.detail === "string") message = body.detail;
      if (Array.isArray(body.detail)) {
        const validationMessage = body.detail.map((item) => item.msg).filter(Boolean).join("；");
        if (validationMessage) message = validationMessage;
      }
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

async function translateTextInBrowser(text: string): Promise<string> {
  // MyMemory explicitly permits browser CORS requests. The anonymous Google
  // endpoint does not, so it cannot be a dependable client-side fallback.
  const url = new URL("https://api.mymemory.translated.net/get");
  url.search = new URLSearchParams({
    q: text,
    langpair: "en|zh-CN",
    mt: "1",
  }).toString();
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`备用翻译失败（${response.status}）`);

  const payload = await response.json() as {
    responseData?: { translatedText?: string };
    responseDetails?: string;
    responseStatus?: number;
    quotaFinished?: boolean;
  };
  if (payload.quotaFinished || (payload.responseStatus ?? 200) !== 200) {
    throw new Error(payload.responseDetails || "备用翻译额度暂不可用");
  }
  const translated = payload.responseData?.translatedText?.trim() ?? "";
  if (!translated || translated.toUpperCase().startsWith("MYMEMORY WARNING")) {
    throw new Error("备用翻译返回了未知格式");
  }
  return translated;
}

export async function translateNews(title: string, summary: string): Promise<NewsTranslation> {
  try {
    return await Promise.race([
      apiRequest<NewsTranslation>("/api/news/translate", undefined, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, summary }),
      }),
      new Promise<never>((_, reject) => {
        window.setTimeout(() => reject(new Error("服务端翻译等待超时")), 4_000);
      }),
    ]);
  } catch {
    try {
      const titleZh = await translateTextInBrowser(title);
      const summaryZh = await translateTextInBrowser(summary);
      return {
        title_zh: titleZh,
        summary_zh: summaryZh,
        provider: "MyMemory（浏览器备用通道）",
      };
    } catch {
      throw new Error("翻译服务暂时繁忙，请稍后重试。");
    }
  }
}

export const getWatchlist = (signal?: AbortSignal) =>
  apiRequest<WatchlistItem[]>("/api/watchlist", signal);

export const addToWatchlist = (coinId: string) =>
  apiRequest<WatchlistItem>(`/api/watchlist/${coinId}`, undefined, { method: "POST" });

export async function removeFromWatchlist(coinId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl()}/api/watchlist/${coinId}`, { method: "DELETE", credentials: "include" });
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
  const response = await fetch(`${apiBaseUrl()}/api/alerts/rules/${ruleId}`, { method: "DELETE", credentials: "include" });
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

export const getCurrentUser = (signal?: AbortSignal) =>
  apiRequest<AuthUser>("/api/auth/me", signal);

export const registerUser = (email: string, password: string) =>
  apiRequest<AuthUser>("/api/auth/register", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

export const loginUser = (email: string, password: string) =>
  apiRequest<AuthUser>("/api/auth/login", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

export const requestPasswordReset = (email: string) =>
  apiRequest<PasswordResetRequestResult>("/api/auth/password-reset/request", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });

export const confirmPasswordReset = (token: string, password: string) =>
  apiRequest<AuthUser>("/api/auth/password-reset/confirm", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });

export async function logoutUser(): Promise<void> {
  const response = await fetch(`${apiBaseUrl()}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok && response.status !== 204) throw new Error("退出登录失败");
}

export const getNotificationSettings = (signal?: AbortSignal) =>
  apiRequest<NotificationSettings>("/api/notifications/settings", signal);

export const updateNotificationSettings = (settings: Pick<NotificationSettings, "email_enabled">) =>
  apiRequest<NotificationSettings>("/api/notifications/settings", undefined, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });

export const sendTestEmail = () =>
  apiRequest<NotificationTestResult>("/api/notifications/test-email", undefined, {
    method: "POST",
  });
