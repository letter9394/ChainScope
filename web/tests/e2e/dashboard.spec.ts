import { expect, test, type Page, type Route } from "@playwright/test";

const now = "2026-09-26T05:00:00Z";
const markets = [
  { id: "bitcoin", symbol: "BTC", name: "Bitcoin", image: null, current_price: 84000, market_cap: 1_670_000_000_000, total_volume: 31_000_000_000, price_change_percentage_24h: 1.2, price_change_percentage_7d: 2.4, last_updated: now, sparkline: [] },
  { id: "ethereum", symbol: "ETH", name: "Ethereum", image: null, current_price: 2700, market_cap: 325_000_000_000, total_volume: 15_000_000_000, price_change_percentage_24h: 0.6, price_change_percentage_7d: 1.1, last_updated: now, sparkline: [] },
  { id: "solana", symbol: "SOL", name: "Solana", image: null, current_price: 120, market_cap: 70_000_000_000, total_volume: 4_000_000_000, price_change_percentage_24h: 2.1, price_change_percentage_7d: 4.2, last_updated: now, sparkline: [] },
  { id: "gold", symbol: "XAU", name: "Gold Spot", image: null, current_price: 4290, market_cap: null, total_volume: null, price_change_percentage_24h: null, price_change_percentage_7d: null, last_updated: now, sparkline: [] },
];

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/markets") return json(route, markets);
    if (url.pathname === "/api/auth/me") return json(route, { detail: "Not authenticated" }, 401);
    if (url.pathname.endsWith("/candles")) {
      const assetId = url.pathname.split("/")[3];
      const interval = url.searchParams.get("interval") ?? "15m";
      const source = url.searchParams.get("source");
      const isGold = assetId === "gold";
      return json(route, {
        asset_id: assetId,
        symbol: isGold ? "PAXGUSDT" : `${assetId.toUpperCase()}USDT`,
        display_symbol: isGold ? "PAXG/USDT" : `${assetId.toUpperCase()}/USDT`,
        interval,
        provider: isGold ? "Binance Spot" : "Binance Spot",
        is_proxy: isGold && source !== "exact",
        proxy_notice: isGold ? "测试用黄金代理行情" : null,
        updated_at: now,
        candles: Array.from({ length: 40 }, (_, index) => ({
          time: 1_790_000_000 + index * 900,
          open: 4200 + index,
          high: 4202 + index,
          low: 4198 + index,
          close: 4201 + index,
          volume: 10 + index,
        })),
      });
    }
    if (url.pathname.endsWith("/risk")) {
      const coinId = url.pathname.split("/")[3];
      return json(route, {
        coin_id: coinId, symbol: "BTC", score: 42, level: "medium", level_label: "中风险",
        summary: "测试风险摘要", metrics: [], sample_days: 30, calculated_at: now, market_context: null,
      });
    }
    if (url.pathname.endsWith("/risk/backtest")) {
      return json(route, {
        coin_id: "bitcoin", symbol: "BTC", model_version: "test", history_days: 365,
        window_days: 30, risk_threshold: 60, hit_threshold_percent: 3, evaluated_points: 300,
        signal_count: 12, sample_start: 1_700_000_000, sample_end: 1_790_000_000,
        horizons: [], recent_signals: [], methodology: "E2E fixture", calculated_at: now,
      });
    }
    if (url.pathname === "/api/news") return json(route, { articles: [], analysis_mode: "rules", notice: "测试数据" });
    return json(route, { detail: "Not found in E2E fixture" }, 404);
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.route("https://www.tradingview-widget.com/**", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bitcoin K线图" })).toBeVisible();
});

test("switches to the real-time TradingView gold chart and changes timeframe", async ({ page }) => {
  await page.getByRole("button", { name: /XAU Gold Spot/ }).click();

  await expect(page.getByRole("heading", { name: "黄金 K线图" })).toBeVisible();
  await expect(page.getByRole("button", { name: "TradingView 实时图" })).toHaveClass(/active/);
  const chart = page.getByTitle("XAU/USD TradingView 实时K线图");
  await expect(chart).toHaveAttribute("src", /OANDA%3AXAUUSD/);
  const firstSource = await chart.getAttribute("src");

  await page.getByLabel("XAU/USD TradingView K线周期").getByRole("button", { name: "5分", exact: true }).click();
  await expect(page.getByTitle("XAU/USD TradingView 实时K线图")).not.toHaveAttribute("src", firstSource ?? "");
});

test("keeps the native gold fallback usable across timeframes", async ({ page }) => {
  await page.getByRole("button", { name: /XAU Gold Spot/ }).click();
  await page.getByRole("button", { name: "站内备用图" }).click();

  await expect(page.getByText("PAXG/USDT", { exact: true })).toBeVisible();
  await expect(page.getByLabel("XAU 站内K线图")).toBeVisible();
  await page.getByLabel("XAU K线周期").getByRole("button", { name: "5分", exact: true }).click();
  await expect(page.getByLabel("XAU K线周期").getByRole("button", { name: "5分", exact: true })).toHaveClass(/active/);
  await expect(page.getByText("Application error", { exact: false })).toHaveCount(0);
});
