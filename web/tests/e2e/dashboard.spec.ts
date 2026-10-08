import { expect, test, type Page, type Route } from "@playwright/test";
import { readFile } from "node:fs/promises";

const now = "2026-09-26T05:00:00Z";
const markets = [
  { id: "bitcoin", symbol: "BTC", name: "Bitcoin", image: null, current_price: 84000, market_cap: 1_670_000_000_000, total_volume: 31_000_000_000, price_change_percentage_24h: 1.2, price_change_percentage_7d: 2.4, last_updated: now, sparkline: [] },
  { id: "ethereum", symbol: "ETH", name: "Ethereum", image: null, current_price: 2700, market_cap: 325_000_000_000, total_volume: 15_000_000_000, price_change_percentage_24h: 0.6, price_change_percentage_7d: 1.1, last_updated: now, sparkline: [] },
  { id: "solana", symbol: "SOL", name: "Solana", image: null, current_price: 120, market_cap: 70_000_000_000, total_volume: 4_000_000_000, price_change_percentage_24h: 2.1, price_change_percentage_7d: 4.2, last_updated: now, sparkline: [] },
  { id: "gold", symbol: "XAU", name: "Gold Spot", image: null, current_price: 4290, market_cap: null, total_volume: null, price_change_percentage_24h: null, price_change_percentage_7d: null, last_updated: now, sparkline: [] },
];

function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) {
  return route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/markets") return json(route, markets);
    if (url.pathname === "/api/auth/me") return json(route, { detail: "Not authenticated" }, 401);
    if (url.pathname === "/api/auth/csrf") {
      return json(
        route,
        { csrf_token: "e2e-csrf-token" },
        200,
        { "Set-Cookie": "chainscope_csrf=e2e-csrf-token; Path=/; SameSite=Lax" },
      );
    }
    if (url.pathname === "/api/auth/register") {
      return json(route, {
        id: 1,
        email: "csrf-e2e@example.com",
        created_at: now,
        email_verified: false,
      }, 201);
    }
    if (url.pathname === "/api/watchlist") return json(route, []);
    if (url.pathname === "/api/alerts/rules") return json(route, []);
    if (url.pathname === "/api/alerts/events") return json(route, []);
    if (url.pathname === "/api/notifications/settings") {
      return json(route, {
        email_enabled: false,
        drift_email_enabled: false,
        in_app_enabled: true,
        email_available: false,
        email_provider: "尚未配置",
        email_sender: null,
        schedule_seconds: 60,
        schedule_mode: "后台定时检查",
      });
    }
    if (url.pathname === "/api/notifications/drift-deliveries") return json(route, []);
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
    if (url.pathname === "/api/risk/backtests") {
      return json(route, {
        model_name: "v0.4 标准化逻辑回归实验",
        target: "未来7日最大跌幅 ≥ 3%",
        required_passing_assets: 2,
        passing_assets: 1,
        available_assets: 3,
        promoted: false,
        verdict: "跨资产门槛未通过：仅 1 个资产达标，至少需要 2 个。",
        label_study_passing_assets: 0,
        label_study_recommended: false,
        label_study_verdict: "跨周期标签门槛未通过：仅 0 个资产在3日与7日周期均独立改善，至少需要 2 个；线上标签保持不变。",
        assets: [
          { coin_id: "bitcoin", symbol: "BTC", status: "validated", baseline_hit_rate_percent: 30, precision_percent: 55.6, recall_percent: 11.1, lift: 1.85, signal_count: 9, passed: true, recommended_label: null, label_improved: false, stable_horizons: 1 },
          { coin_id: "ethereum", symbol: "ETH", status: "validated", baseline_hit_rate_percent: 36, precision_percent: 32, recall_percent: 8, lift: 0.89, signal_count: 8, passed: false, recommended_label: null, label_improved: false, stable_horizons: 0 },
          { coin_id: "solana", symbol: "SOL", status: "validated", baseline_hit_rate_percent: 42, precision_percent: 38, recall_percent: 6, lift: 0.9, signal_count: 6, passed: false, recommended_label: null, label_improved: false, stable_horizons: 0 },
        ],
        calculated_at: now,
      });
    }
    if (url.pathname === "/api/risk/drift") {
      const current = {
        id: 2,
        coin_id: "bitcoin",
        symbol: "BTC",
        status: "deteriorating",
        selected_key: "fixed",
        selected_label: "固定跌幅",
        horizon_days: 7,
        lift_change: -0.62,
        brier_skill_change: -0.115,
        event_rate_change_percent_points: 4.2,
        latest_lift: 0.73,
        latest_brier_skill_score: -0.035,
        observed_at: now,
      };
      return json(route, {
        model_name: "v0.8 模型漂移告警闭环",
        status: "degraded",
        interval_seconds: 21_600,
        last_checked_at: now,
        assets: [
          { coin_id: "bitcoin", symbol: "BTC", current, history: [current] },
          { coin_id: "ethereum", symbol: "ETH", current: null, history: [] },
          { coin_id: "solana", symbol: "SOL", current: null, history: [] },
        ],
        events: [{
          id: 1,
          coin_id: "bitcoin",
          symbol: "BTC",
          previous_status: "stable",
          current_status: "deteriorating",
          severity: "warning",
          title: "BTC 模型检测到性能衰减",
          message: "最近留出期表现相对早期下降，已进入人工复核队列；线上模型不会自动切换。",
          created_at: now,
        }],
      });
    }
    if (url.pathname.endsWith("/risk/backtest")) {
      const coinId = url.pathname.split("/")[3];
      const symbol = coinId === "ethereum" ? "ETH" : coinId === "solana" ? "SOL" : "BTC";
      return json(route, {
        coin_id: coinId, symbol, model_version: "test", history_days: 365,
        window_days: 30, risk_threshold: 60, hit_threshold_percent: 3, evaluated_points: 300,
        signal_count: 12, sample_start: 1_700_000_000, sample_end: 1_790_000_000,
        horizons: [],
        regimes: [
          { regime: "bull", label: "上涨阶段", signal_count: 4, hit_count: 2, hit_rate_percent: 50, average_max_drawdown_percent: 2.5 },
          { regime: "bear", label: "下跌阶段", signal_count: 4, hit_count: 3, hit_rate_percent: 75, average_max_drawdown_percent: 4.1 },
          { regime: "sideways", label: "震荡阶段", signal_count: 4, hit_count: 2, hit_rate_percent: 50, average_max_drawdown_percent: 2.9 },
        ],
        validation: {
          horizon_days: 7, split_timestamp: 1_760_000_000, training_points: 210,
          holdout_points: 90, training_signal_count: 8, holdout_signal_count: 4,
          training_hit_rate_percent: 62.5, holdout_hit_rate_percent: 50,
        },
        sensitivity: [
          { threshold: 50, horizon_days: 7, signal_count: 16, hit_rate_percent: 50, average_max_drawdown_percent: 2.6 },
          { threshold: 60, horizon_days: 7, signal_count: 12, hit_rate_percent: 58.3, average_max_drawdown_percent: 3.1 },
          { threshold: 70, horizon_days: 7, signal_count: 6, hit_rate_percent: 66.7, average_max_drawdown_percent: 3.8 },
        ],
        quality: {
          horizon_days: 7, evaluated_days: 300, event_days: 90, signal_count: 12,
          true_positive_count: 7, false_positive_count: 5, false_negative_count: 83,
          true_negative_count: 205, baseline_hit_rate_percent: 30, accuracy_percent: 70.7,
          precision_percent: 58.3, recall_percent: 7.8, miss_rate_percent: 92.2, lift: 1.94,
        },
        walk_forward: {
          horizon_days: 7, embargo_days: 7, candidate_thresholds: [40, 45, 50, 55, 60, 65, 70, 75, 80],
          total_holdout_points: 150, event_days: 45, signal_count: 6,
          baseline_hit_rate_percent: 30, accuracy_percent: 70.7, precision_percent: 50,
          recall_percent: 6.7, miss_rate_percent: 93.3, lift: 1.67,
          folds: [1, 2, 3].map((fold) => ({
            fold, selected_threshold: 55 + fold * 5, training_points: 140 + fold * 50,
            holdout_points: 50, holdout_start: 1_740_000_000 + fold * 10_000_000,
            holdout_end: 1_750_000_000 + fold * 10_000_000, holdout_event_count: 15,
            holdout_signal_count: 2, baseline_hit_rate_percent: 30, precision_percent: 50,
            recall_percent: 6.7, lift: 1.67,
          })),
        },
        feature_model: {
          status: "validated", model_name: "v0.4 标准化逻辑回归实验", target: "未来7日最大跌幅 ≥ 3%",
          horizon_days: 7, lookback_days: 90, embargo_days: 7, total_holdout_points: 150,
          event_days: 45, signal_count: 9, baseline_hit_rate_percent: 30, accuracy_percent: 72,
          precision_percent: 55.6, recall_percent: 11.1, miss_rate_percent: 88.9, lift: 1.85,
          promoted: true, verdict: "通过晋级门槛：留出期相对市场基准有稳定增益，可进入影子运行。",
          feature_importance: [
            { key: "drawdown_30d", label: "30日回撤", coefficient: 0.82, direction: "raises_risk" },
            { key: "volatility_ratio", label: "短长波动率比", coefficient: 0.61, direction: "raises_risk" },
            { key: "momentum_30d", label: "30日动量", coefficient: -0.45, direction: "lowers_risk" },
          ],
          folds: [1, 2, 3].map((fold) => ({
            fold, probability_threshold_percent: 45 + fold * 5, training_points: 130 + fold * 50,
            holdout_points: 50, holdout_start: 1_740_000_000 + fold * 10_000_000,
            holdout_end: 1_750_000_000 + fold * 10_000_000, holdout_event_count: 15,
            holdout_signal_count: 3, baseline_hit_rate_percent: 30, precision_percent: 55.6,
            recall_percent: 11.1, lift: 1.85,
          })),
        },
        label_study: {
          model_name: "v0.5 标签与概率校准实验",
          horizon_days: 7,
          status: "validated",
          recommended_key: "volatility",
          recommended: true,
          verdict: "波动率归一化同时改善 Lift 与 Brier Score，可进入跨资产复核。",
          experiments: [
            { key: "fixed", label: "固定跌幅", target: "未来7日最大跌幅 ≥ 3%", status: "validated", total_holdout_points: 150, event_days: 45, signal_count: 9, baseline_hit_rate_percent: 30, precision_percent: 55.6, recall_percent: 11.1, lift: 1.85, brier_score: 0.2241, brier_skill_score: -0.067, calibration_error_percent: 9.8, precision_confidence_interval: { lower: 28.6, upper: 77.8, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, lift_confidence_interval: { lower: 0.92, upper: 2.68, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, brier_confidence_interval: { lower: 0.1901, upper: 0.2598, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, folds: [] },
            { key: "volatility", label: "波动率归一化", target: "未来7日跌幅超过历史波动自适应阈值", status: "validated", total_holdout_points: 150, event_days: 36, signal_count: 8, baseline_hit_rate_percent: 24, precision_percent: 62.5, recall_percent: 13.9, lift: 2.6, brier_score: 0.1812, brier_skill_score: 0.007, calibration_error_percent: 7.1, precision_confidence_interval: { lower: 40, upper: 87.5, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, lift_confidence_interval: { lower: 1.18, upper: 3.92, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, brier_confidence_interval: { lower: 0.149, upper: 0.216, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, folds: [] },
            { key: "quantile", label: "训练集最差25%", target: "未来7日跌幅进入训练集最差25%", status: "validated", total_holdout_points: 150, event_days: 38, signal_count: 7, baseline_hit_rate_percent: 25.3, precision_percent: 42.9, recall_percent: 7.9, lift: 1.69, brier_score: 0.2022, brier_skill_score: -0.070, calibration_error_percent: 8.6, precision_confidence_interval: { lower: 14.3, upper: 71.4, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, lift_confidence_interval: { lower: 0.51, upper: 2.9, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, brier_confidence_interval: { lower: 0.171, upper: 0.238, confidence_level_percent: 95, method: "14日循环区块Bootstrap", resamples: 500, block_days: 14 }, folds: [] },
          ],
        },
        label_stability: {
          model_name: "v0.6 跨周期稳定性审查",
          required_horizons: [3, 7],
          consistent_key: null,
          stable: false,
          verdict: "替代标签尚未在3日、7日周期同时通过，继续保留固定3%标签。",
          horizons: [
            { horizon_days: 3, status: "validated", selected_key: "fixed", selected_label: "固定跌幅", lift: 1.41, lift_confidence_lower: 0.79, brier_skill_score: -0.021, passed: false, verdict: "3日周期未通过。" },
            { horizon_days: 7, status: "validated", selected_key: "volatility", selected_label: "波动率归一化", lift: 2.6, lift_confidence_lower: 1.18, brier_skill_score: 0.007, passed: true, verdict: "7日周期通过。" },
          ],
        },
        temporal_stability: {
          model_name: "v0.7 时间稳定性与漂移监控",
          status: "deteriorating",
          selected_key: "fixed",
          selected_label: "固定跌幅",
          horizon_days: 7,
          lift_change: -0.62,
          brier_skill_change: -0.115,
          event_rate_change_percent_points: 4.2,
          verdict: "固定跌幅最近留出期相对首期出现性能衰减；仅作为监控告警，不会自动改变线上风险模型。",
          periods: [
            { period: 1, holdout_start: 1_740_000_000_000, holdout_end: 1_744_000_000_000, holdout_points: 50, event_days: 15, signal_count: 3, baseline_hit_rate_percent: 30, precision_percent: 66.7, lift: 2.22, brier_skill_score: 0.08, calibration_error_percent: 6, passed: true },
            { period: 2, holdout_start: 1_744_086_400_000, holdout_end: 1_748_086_400_000, holdout_points: 50, event_days: 16, signal_count: 2, baseline_hit_rate_percent: 32, precision_percent: 50, lift: 1.56, brier_skill_score: 0.02, calibration_error_percent: 8, passed: true },
            { period: 3, holdout_start: 1_748_172_800_000, holdout_end: 1_752_172_800_000, holdout_points: 50, event_days: 17, signal_count: 2, baseline_hit_rate_percent: 34.2, precision_percent: 25, lift: 0.73, brier_skill_score: -0.035, calibration_error_percent: 12, passed: false },
          ],
        },
        recent_signals: [], methodology: "E2E fixture", calculated_at: now,
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

test("shows base-rate lift and walk-forward validation", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "跨资产晋级审查" })).toBeVisible();
  await expect(page.getByText("跨资产暂不晋级", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "模型有效性" })).toBeVisible();
  await expect(page.getByText("1.94×", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Walk-forward 滚动验证" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "第 3 轮", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "v0.4 特征模型实验" })).toBeVisible();
  await expect(page.getByText("单资产候选通过", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "v0.5 标签与概率校准实验" })).toBeVisible();
  await expect(page.getByText("2.60× Lift", { exact: true })).toBeVisible();
  await expect(page.getByText("1.18–3.92", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "v0.6 跨周期稳定性审查" })).toBeVisible();
  await expect(page.getByText("跨周期结果不稳定", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "v0.7 时间稳定性与漂移监控" })).toBeVisible();
  await expect(page.getByText("检测到性能衰减", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "v0.8 模型漂移告警闭环" })).toBeVisible();
  await expect(page.getByText("BTC 模型检测到性能衰减", { exact: true })).toBeVisible();
  await expect(page.locator("section.backtest-drift-monitor .backtest-walk-summary strong").filter({ hasText: "0.73×" })).toBeVisible();
});

test("switches backtest assets from the cross-asset review", async ({ page }) => {
  await page.getByRole("button", { name: "查看 ETH 回测" }).click();
  await expect(page.getByRole("heading", { name: "ETH 高风险信号回测" })).toBeVisible();
  await expect(page.getByRole("button", { name: /ETH Ethereum/ })).toHaveClass(/active/);
});

test("attaches a CSRF token before account registration", async ({ page }) => {
  await page.locator("#account").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.getByLabel("邮箱").fill("csrf-e2e@example.com");
  await page.getByLabel("密码").fill("safe-password-1");

  const registrationRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname === "/api/auth/register",
  );
  await page.getByRole("button", { name: "创建账号" }).click();
  const request = await registrationRequest;

  expect(request.headers()["x-csrf-token"]).toBe("e2e-csrf-token");
  await expect(page.getByRole("heading", { name: "csrf-e2e@example.com" })).toBeVisible();
});

test("shows the signed-in user's drift email delivery history", async ({ page }) => {
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 7, email: "history@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/notifications/drift-deliveries", (route) => json(route, [{
    event_id: 19, coin_id: "bitcoin", symbol: "BTC", title: "BTC 模型检测到性能衰减",
    status: "sent", attempted_at: now,
  }, {
    event_id: 20, coin_id: "ethereum", symbol: "ETH", title: "ETH 模型检测到性能衰减",
    status: "delivered", attempted_at: now, provider_event_at: now,
  }]));
  await page.reload();

  await expect(page.getByRole("heading", { name: "history@example.com" })).toBeVisible();
  const history = page.getByRole("region", { name: "模型漂移邮件投递记录" });
  await expect(history).toContainText("BTC 模型检测到性能衰减");
  await expect(history).toContainText("服务商已接收");
  await expect(history).toContainText("已送达");
});

test("downloads signed-in account data as a JSON file", async ({ page }) => {
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 7, email: "export@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/account/export", (route) => json(route, {
    format: "chainscope-account-export", schema_version: 1,
    account: { email: "export@example.com" }, watchlist: [], alert_rules: [], alert_events: [],
  }));
  await page.reload();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "下载我的数据" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^chainscope-account-data-\d{4}-\d{2}-\d{2}\.json$/);
  const payload = JSON.parse(await readFile(await download.path(), "utf8"));
  expect(payload.account.email).toBe("export@example.com");
  await expect(page.getByRole("status").filter({ hasText: "个人数据文件已开始下载" })).toBeVisible();
});

test("creates, triggers, acknowledges and safely deletes an alert rule", async ({ page }) => {
  type TestRule = {
    id: number; coin_id: string; symbol: string; metric: string; operator: string;
    threshold: number; enabled: boolean; is_triggered: boolean;
    created_at: string; last_triggered_at: string | null;
  };
  type TestEvent = {
    id: number; rule_id: number; coin_id: string; symbol: string; metric: string;
    operator: string; threshold: number; observed_value: number; severity: string;
    title: string; message: string; triggered_at: string; acknowledged_at: string | null;
  };
  const rules: TestRule[] = [];
  const events: TestEvent[] = [];
  let evaluations = 0;

  await page.route("**/api/auth/me", (route) => json(route, {
    id: 7, email: "alerts-e2e@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/alerts/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (pathname === "/api/alerts/rules" && method === "GET") return json(route, rules);
    if (pathname === "/api/alerts/events" && method === "GET") return json(route, events);
    if (pathname === "/api/alerts/rules" && method === "POST") {
      const input = route.request().postDataJSON();
      const rule = {
        ...input, id: 1, symbol: "BTC", enabled: true, is_triggered: false,
        created_at: now, last_triggered_at: null,
      };
      rules.unshift(rule);
      return json(route, rule, 201);
    }
    if (pathname === "/api/alerts/evaluate" && method === "POST") {
      evaluations += 1;
      const triggered: TestEvent[] = [];
      if (rules[0] && !rules[0].is_triggered) {
        rules[0].is_triggered = true;
        rules[0].last_triggered_at = now;
        const event = {
          id: 1, rule_id: 1, coin_id: "bitcoin", symbol: "BTC", metric: "price_change_24h",
          operator: "lte", threshold: -5, observed_value: -6, severity: "warning",
          title: "BTC 24 小时涨跌幅已越过阈值", message: "当前值 -6%，已达到阈值。",
          triggered_at: now, acknowledged_at: null,
        };
        events.unshift(event);
        triggered.push(event);
      }
      return json(route, { evaluated_rules: rules.length, triggered_events: triggered,
        active_events: events.filter((event) => !event.acknowledged_at) });
    }
    if (pathname === "/api/alerts/events/1/acknowledge" && method === "POST") {
      events[0].acknowledged_at = now;
      return json(route, events[0]);
    }
    if (pathname === "/api/alerts/rules/1" && method === "DELETE") {
      rules.length = 0;
      events.length = 0;
      return route.fulfill({ status: 204, body: "" });
    }
    return json(route, { detail: "Unexpected alert request" }, 404);
  });
  await page.reload();

  const alerts = page.locator("#alerts");
  await expect(alerts.locator(".alert-journey")).toContainText("设置规则");
  await alerts.getByLabel("指标").selectOption("price_change_24h");
  await alerts.getByRole("button", { name: "保存这条提醒" }).click();
  await expect(alerts.getByRole("status").filter({ hasText: "规则已保存，并产生了新预警" })).toBeVisible();
  await expect(alerts.getByRole("heading", { name: "BTC 24 小时涨跌幅已越过阈值" })).toBeVisible();

  await alerts.getByRole("button", { name: "立即检查" }).click();
  await expect(alerts.getByText("检查完成，本次没有新增预警", { exact: false })).toBeVisible();
  expect(evaluations).toBe(2);
  await expect(alerts.locator(".event-item")).toHaveCount(1);

  await alerts.getByRole("button", { name: "我知道了" }).click();
  await expect(alerts.locator(".event-item")).toContainText("已确认");
  await expect(alerts.getByText("0 条待确认")).toBeVisible();

  page.once("dialog", (dialog) => dialog.dismiss());
  await alerts.getByRole("button", { name: "删除 BTC 预警规则" }).click();
  await expect(alerts.locator(".rule-item")).toHaveCount(1);
  page.once("dialog", (dialog) => dialog.accept());
  await alerts.getByRole("button", { name: "删除 BTC 预警规则" }).click();
  await expect(alerts.getByText("规则及关联的预警历史已删除。")).toBeVisible();
  await expect(alerts.locator(".rule-item")).toHaveCount(0);
  await expect(alerts.locator(".event-item")).toHaveCount(0);
});

test("marks active zero-point risk rules as demo thresholds without changing them", async ({ page }) => {
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 9, email: "demo-rule-e2e@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/alerts/rules", (route) => json(route, [1, 2].map((id) => ({
    id, coin_id: "bitcoin", symbol: "BTC", metric: "risk_score", operator: "gte",
    threshold: 0, enabled: true, is_triggered: true, created_at: now, last_triggered_at: now,
  }))));
  await page.reload();

  const alerts = page.locator("#alerts");
  await expect(alerts.locator(".alert-demo-warning")).toContainText("2 条已启用的 0 分验收规则");
  await expect(alerts.locator(".rule-item")).toHaveCount(2);
  await expect(alerts.locator(".rule-item").first()).toContainText("演示阈值");
  await alerts.locator(".threshold-input input").fill("0");
  await expect(alerts.locator(".demo-threshold-hint")).toBeVisible();
});

test("pauses and resumes a rule while keeping its event visible", async ({ page }) => {
  const rule = {
    id: 11, coin_id: "bitcoin", symbol: "BTC", metric: "risk_score", operator: "gte",
    threshold: 0, enabled: true, is_triggered: true, created_at: now, last_triggered_at: now,
  };
  const event = {
    id: 12, rule_id: 11, coin_id: "bitcoin", symbol: "BTC", metric: "risk_score",
    operator: "gte", threshold: 0, observed_value: 12, severity: "warning",
    title: "BTC 综合风险分已越过阈值", message: "测试事件", triggered_at: now, acknowledged_at: null,
  };
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 9, email: "pause-rule-e2e@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/alerts/rules", (route) => json(route, [rule]));
  await page.route("**/api/alerts/events?*", (route) => json(route, [event]));
  await page.route("**/api/alerts/rules/11", (route) => {
    expect(route.request().method()).toBe("PATCH");
    rule.enabled = route.request().postDataJSON().enabled;
    return json(route, rule);
  });
  await page.reload();

  const alerts = page.locator("#alerts");
  await expect(alerts.locator(".event-item")).toHaveCount(1);
  await alerts.getByRole("button", { name: "停用 BTC · 综合风险分 ≥ 0分" }).click();
  await expect(alerts.locator(".rule-item")).toContainText("已停用 · 演示阈值");
  await expect(alerts.locator(".event-item")).toHaveCount(1);
  await expect(alerts.locator(".alert-demo-warning")).toHaveCount(0);
  await alerts.getByRole("button", { name: "启用 BTC · 综合风险分 ≥ 0分" }).click();
  await expect(alerts.locator(".alert-demo-warning")).toBeVisible();
  await expect(alerts.locator(".event-item")).toHaveCount(1);
});

test("keeps the alert setup readable on a narrow phone", async ({ page }) => {
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 8, email: "phone-e2e@example.com", created_at: now, email_verified: true,
  }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const alerts = page.locator("#alerts");
  await alerts.scrollIntoViewIfNeeded();
  await expect(alerts.getByRole("heading", { name: "设置监控规则" })).toBeVisible();
  await expect(alerts.getByRole("button", { name: "保存这条提醒" })).toBeVisible();
  await expect(alerts.getByRole("heading", { name: "预警事件" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
});

test("shows alert-save failures beside the form", async ({ page }) => {
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 9, email: "error-e2e@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/alerts/rules", (route) =>
    route.request().method() === "POST"
      ? json(route, { detail: "预警服务暂时不可用" }, 503)
      : json(route, []),
  );
  await page.reload();
  const alerts = page.locator("#alerts");
  await alerts.getByRole("button", { name: "保存这条提醒" }).click();
  await expect(alerts.getByRole("alert")).toContainText("保存失败");
  await expect(alerts.locator(".rule-item")).toHaveCount(0);
});

test("warns about an identical alert rule without sending another create request", async ({ page }) => {
  let createRequests = 0;
  await page.route("**/api/auth/me", (route) => json(route, {
    id: 11, email: "duplicate-e2e@example.com", created_at: now, email_verified: true,
  }));
  await page.route("**/api/alerts/rules", (route) => {
    if (route.request().method() === "POST") {
      createRequests += 1;
      return json(route, { detail: "相同的预警规则已存在，请在下方查看已有规则。" }, 409);
    }
    return json(route, [{
      id: 12, coin_id: "bitcoin", symbol: "BTC", metric: "risk_score", operator: "gte",
      threshold: 65, enabled: true, is_triggered: false, created_at: now, last_triggered_at: null,
    }]);
  });
  await page.reload();

  const alerts = page.locator("#alerts");
  await expect(alerts.locator(".rule-item")).toHaveCount(1);
  await alerts.getByRole("button", { name: "保存这条提醒" }).click();
  await expect(alerts.getByRole("status").filter({ hasText: "相同的预警规则已存在" })).toBeVisible();
  await expect(alerts.locator(".rule-item")).toHaveCount(1);
  expect(createRequests).toBe(0);
});

test("shows a loading state instead of a login prompt while checking the session", async ({ page }) => {
  let finishSessionCheck: () => void = () => undefined;
  const sessionCheck = new Promise<void>((resolve) => { finishSessionCheck = resolve; });
  await page.route("**/api/auth/me", async (route) => {
    await sessionCheck;
    await json(route, { id: 10, email: "loading-e2e@example.com", created_at: now, email_verified: true });
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  const alerts = page.locator("#alerts");
  await expect(alerts.getByRole("status")).toContainText("正在读取账号和预警记录");
  await expect(alerts.getByText("登录后启用个人风险预警")).toHaveCount(0);
  finishSessionCheck();
  await expect(alerts.getByRole("heading", { name: "设置监控规则" })).toBeVisible();
});
