"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AlertCenter } from "@/components/AlertCenter";
import { AccountPanel } from "@/components/AccountPanel";
import { DerivativesPanel } from "@/components/DerivativesPanel";
import { MarketCard } from "@/components/MarketCard";
import { NewsPanel } from "@/components/NewsPanel";
import { RiskPanel } from "@/components/RiskPanel";
import { RiskBacktestPanel } from "@/components/RiskBacktestPanel";
import { CandlestickChart } from "@/components/CandlestickChart";
import { ChartErrorBoundary } from "@/components/ChartErrorBoundary";
import { useLiveCryptoPrices } from "@/hooks/useLiveCryptoPrices";
import { useLiquidationStream } from "@/hooks/useLiquidationStream";
import {
  addToWatchlist,
  acknowledgeAlertEvent,
  confirmEmailVerification,
  createAlertRule,
  confirmPasswordReset,
  deleteAlertRule,
  evaluateAlerts,
  getCurrentUser,
  getAlertEvents,
  getAlertRules,
  getMarkets,
  getNews,
  getNotificationSettings,
  getRisk,
  getRiskBacktest,
  getWatchlist,
  loginUser,
  logoutUser,
  registerUser,
  resendEmailVerification,
  requestPasswordReset,
  removeFromWatchlist,
  sendTestEmail,
  updateNotificationSettings,
} from "@/lib/api";
import type {
  AlertEvent,
  AlertRule,
  AlertRuleInput,
  AuthUser,
  MarketCoin,
  NewsResponse,
  NotificationSettings,
  RiskAssessment,
  RiskBacktestResult,
} from "@/lib/types";

interface ChartQuote {
  assetId: string;
  price: number;
  displaySymbol: string;
  isProxy: boolean;
}

const priceCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const MARKET_REFRESH_MS = 15_000;
const RISK_REFRESH_MS = 10_000;
const ALERT_REFRESH_MS = 60_000;

export default function Home() {
  const [markets, setMarkets] = useState<MarketCoin[]>([]);
  const [selectedId, setSelectedId] = useState("bitcoin");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [riskBacktest, setRiskBacktest] = useState<RiskBacktestResult | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(true);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [news, setNews] = useState<NewsResponse | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [accountBusy, setAccountBusy] = useState(false);
  const [passwordResetToken, setPasswordResetToken] = useState<string | null>(null);
  const [emailVerificationToken, setEmailVerificationToken] = useState<string | null>(null);
  const [emailVerificationMessage, setEmailVerificationMessage] = useState<string | null>(null);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alertEvents, setAlertEvents] = useState<AlertEvent[]>([]);
  const [alertsBusy, setAlertsBusy] = useState(false);
  const [watchlistBusy, setWatchlistBusy] = useState(false);
  const [loadingMarkets, setLoadingMarkets] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chartQuote, setChartQuote] = useState<ChartQuote | null>(null);
  const liveMarketStatus = useLiveCryptoPrices(setMarkets);
  const liquidationStats = useLiquidationStream(selectedId);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setPasswordResetToken(query.get("reset_token"));
    setEmailVerificationToken(query.get("verify_email_token"));
  }, []);

  const selectedCoin = useMemo(
    () => markets.find((coin) => coin.id === selectedId) ?? markets[0],
    [markets, selectedId],
  );
  const selectedChartQuote = selectedId === "gold" && chartQuote?.assetId === selectedId
    ? chartQuote
    : null;
  const displayedPanelPrice = selectedChartQuote?.price ?? selectedCoin?.current_price;
  const activeAlerts = useMemo(
    () => alertEvents.filter((event) => !event.acknowledged_at),
    [alertEvents],
  );

  const loadMarkets = useCallback(async (signal?: AbortSignal) => {
    setLoadingMarkets(true);
    try {
      const result = await getMarkets(signal);
      setMarkets(result);
      setError(null);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(reason instanceof Error ? reason.message : "行情加载失败");
      }
    } finally {
      setLoadingMarkets(false);
    }
  }, []);

  const loadAlertData = useCallback(async (signal?: AbortSignal) => {
    const [rules, events] = await Promise.all([
      getAlertRules(signal),
      getAlertEvents(signal),
    ]);
    setAlertRules(rules);
    setAlertEvents(events);
  }, []);

  const loadPrivateData = useCallback(async (signal?: AbortSignal) => {
    const [watchlistItems, rules, events, settings] = await Promise.all([
      getWatchlist(signal),
      getAlertRules(signal),
      getAlertEvents(signal),
      getNotificationSettings(signal),
    ]);
    setWatchlist(watchlistItems.map((item) => item.coin_id));
    setAlertRules(rules);
    setAlertEvents(events);
    setNotificationSettings(settings);
  }, []);

  useEffect(() => {
    if (!emailVerificationToken) return;
    let active = true;
    setAccountBusy(true);
    void confirmEmailVerification(emailVerificationToken)
      .then(async (verifiedUser) => {
        if (!active) return;
        setUser(verifiedUser);
        await loadPrivateData();
        if (active) {
          setEmailVerificationMessage("邮箱验证成功，邮件风险预警现在可以启用了。");
          setError(null);
        }
      })
      .catch((reason) => {
        if (!active) return;
        const message = reason instanceof Error ? reason.message : "邮箱验证失败";
        setEmailVerificationMessage(message);
        setError(message);
      })
      .finally(() => {
        if (!active) return;
        setAccountBusy(false);
        setEmailVerificationToken(null);
        const url = new URL(window.location.href);
        url.searchParams.delete("verify_email_token");
        window.history.replaceState({}, "", `${url.pathname}${url.search}#account`);
      });
    return () => {
      active = false;
    };
  }, [emailVerificationToken, loadPrivateData]);

  const checkAlerts = useCallback(async () => {
    if (!user) return;
    setAlertsBusy(true);
    try {
      await evaluateAlerts();
      await loadAlertData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警检查失败");
    } finally {
      setAlertsBusy(false);
    }
  }, [loadAlertData, user]);

  useEffect(() => {
    const controller = new AbortController();
    void loadMarkets(controller.signal);
    const marketRefreshTimer = window.setInterval(() => void loadMarkets(), MARKET_REFRESH_MS);
    return () => {
      controller.abort();
      window.clearInterval(marketRefreshTimer);
    };
  }, [loadMarkets]);

  useEffect(() => {
    const controller = new AbortController();
    void getCurrentUser(controller.signal)
      .then(async (currentUser) => {
        setUser(currentUser);
        await loadPrivateData(controller.signal);
      })
      .catch(() => {
        setUser(null);
        setWatchlist([]);
        setAlertRules([]);
        setAlertEvents([]);
      });
    return () => controller.abort();
  }, [loadPrivateData]);

  useEffect(() => {
    if (!user) return;
    const alertRefreshTimer = window.setInterval(() => {
      void getAlertEvents().then(setAlertEvents).catch(() => undefined);
    }, ALERT_REFRESH_MS);
    return () => window.clearInterval(alertRefreshTimer);
  }, [user]);

  const authenticate = async (mode: "login" | "register", email: string, password: string) => {
    setAccountBusy(true);
    try {
      const authenticated = mode === "login" ? await loginUser(email, password) : await registerUser(email, password);
      setUser(authenticated);
      await loadPrivateData();
      setEmailVerificationMessage(
        mode === "register" && !authenticated.email_verified
          ? "账号已创建。验证邮件已经发送；若暂未收到，可以点击重新发送。"
          : null,
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    } finally {
      setAccountBusy(false);
    }
  };

  const clearPasswordResetToken = useCallback(() => {
    setPasswordResetToken(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("reset_token");
    window.history.replaceState({}, "", `${url.pathname}${url.search}#account`);
  }, []);

  const sendPasswordReset = async (email: string) => {
    setAccountBusy(true);
    try {
      const result = await requestPasswordReset(email);
      setError(null);
      return result.message;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "重置邮件发送失败";
      setError(message);
      throw new Error(message);
    } finally {
      setAccountBusy(false);
    }
  };

  const resetPassword = async (token: string, password: string) => {
    setAccountBusy(true);
    try {
      const authenticated = await confirmPasswordReset(token, password);
      setUser(authenticated);
      clearPasswordResetToken();
      await loadPrivateData();
      setError(null);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "密码重置失败";
      setError(message);
      throw new Error(message);
    } finally {
      setAccountBusy(false);
    }
  };

  const logout = async () => {
    setAccountBusy(true);
    try {
      await logoutUser();
      setUser(null);
      setWatchlist([]);
      setAlertRules([]);
      setAlertEvents([]);
      setNotificationSettings(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "退出登录失败");
    } finally {
      setAccountBusy(false);
    }
  };

  const saveNotificationSettings = async (settings: Pick<NotificationSettings, "email_enabled">) => {
    setAccountBusy(true);
    try {
      setNotificationSettings(await updateNotificationSettings(settings));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "通知设置保存失败");
    } finally {
      setAccountBusy(false);
    }
  };

  const testEmailNotification = async () => {
    setAccountBusy(true);
    try {
      const result = await sendTestEmail();
      setError(null);
      return result.message;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "测试邮件发送失败";
      setError(message);
      throw new Error(message);
    } finally {
      setAccountBusy(false);
    }
  };

  const resendVerification = async () => {
    setAccountBusy(true);
    try {
      const result = await resendEmailVerification();
      setEmailVerificationMessage(result.message);
      setError(null);
      return result.message;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "验证邮件发送失败";
      setError(message);
      throw new Error(message);
    } finally {
      setAccountBusy(false);
    }
  };

  const createRule = async (input: AlertRuleInput) => {
    setAlertsBusy(true);
    try {
      await createAlertRule(input);
      await evaluateAlerts();
      await loadAlertData();
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警规则创建失败");
    } finally {
      setAlertsBusy(false);
    }
  };

  const deleteRule = async (ruleId: number) => {
    setAlertsBusy(true);
    try {
      await deleteAlertRule(ruleId);
      setAlertRules((rules) => rules.filter((rule) => rule.id !== ruleId));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警规则删除失败");
    } finally {
      setAlertsBusy(false);
    }
  };

  const acknowledgeEvent = async (eventId: number) => {
    setAlertsBusy(true);
    try {
      const acknowledged = await acknowledgeAlertEvent(eventId);
      setAlertEvents((events) => events.map((event) => event.id === eventId ? acknowledged : event));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警确认失败");
    } finally {
      setAlertsBusy(false);
    }
  };

  const toggleWatchlist = async () => {
    if (!selectedCoin || watchlistBusy) return;
    if (!user) {
      setError("请先登录，再保存个人自选资产。");
      document.querySelector("#account")?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    setWatchlistBusy(true);
    try {
      if (watchlist.includes(selectedCoin.id)) {
        await removeFromWatchlist(selectedCoin.id);
        setWatchlist((items) => items.filter((item) => item !== selectedCoin.id));
      } else {
        await addToWatchlist(selectedCoin.id);
        setWatchlist((items) => [...new Set([...items, selectedCoin.id])]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自选列表更新失败");
    } finally {
      setWatchlistBusy(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    setLoadingDetail(true);
    setRisk(null);
    const detailRequest = selectedId === "gold"
      ? Promise.all([Promise.resolve(null), getNews(selectedId, 6, controller.signal)])
      : Promise.all([
          getRisk(selectedId, 30, controller.signal),
          getNews(selectedId, 6, controller.signal),
        ]);
    detailRequest
      .then(([riskResult, newsResult]) => {
        setRisk(riskResult);
        setNews(newsResult);
        setError(null);
      })
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "风险分析加载失败");
        }
      })
      .finally(() => setLoadingDetail(false));
    return () => controller.abort();
  }, [selectedId]);

  useEffect(() => {
    if (selectedId === "gold") return;
    const refreshTimer = window.setInterval(() => {
      void getRisk(selectedId, 30)
        .then((result) => setRisk(result))
        .catch(() => undefined);
    }, RISK_REFRESH_MS);
    return () => window.clearInterval(refreshTimer);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    setRiskBacktest(null);
    setBacktestError(null);
    if (selectedId === "gold") {
      setBacktestLoading(false);
      return () => controller.abort();
    }
    setBacktestLoading(true);
    void getRiskBacktest(selectedId, controller.signal)
      .then((result) => setRiskBacktest(result))
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setBacktestError(reason instanceof Error ? reason.message : "历史回测加载失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setBacktestLoading(false);
      });
    return () => controller.abort();
  }, [selectedId]);

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="ChainScope 首页">
          <span className="brand-mark">CS</span>
          <span>ChainScope</span>
        </a>
        <div className={`live-status ${liveMarketStatus}`} role="status" aria-live="polite">
          <i /> {liveMarketStatus === "live" ? "实时行情已连接" : liveMarketStatus === "connecting" ? "正在连接实时行情" : "15秒轮询模式"}
        </div>
        <a className="account-link" href="#account">{user ? user.email : "登录 / 注册"}</a>
        <a className="github-link" href="https://github.com/letter9394/ChainScope" target="_blank" rel="noreferrer">
          GitHub ↗
        </a>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="kicker">DIGITAL ASSETS · GOLD · RISK ALERTS</p>
          <h1>看见波动，也看懂风险。</h1>
          <p className="hero-copy">
            ChainScope 将加密资产与黄金行情、专业 K 线、新闻情绪和可解释风险信号集中在一个界面。
            支持从分钟线到周线的多周期观察，适合研究、学习与市场跟踪。
          </p>
        </div>
        <div className="hero-meta">
          <span>行情来源</span><strong>Binance · Gold API · 服务器转发</strong>
          <span>K线周期</span><strong>1 分钟 — 周线</strong>
          <span>行情更新</span><strong>{liveMarketStatus === "live" ? "约 1 秒实时推送" : "每 15 秒"}</strong>
        </div>
      </section>

      <AccountPanel
        user={user}
        settings={notificationSettings}
        busy={accountBusy}
        passwordResetToken={passwordResetToken}
        emailVerificationMessage={emailVerificationMessage}
        onAuthenticate={authenticate}
        onRequestPasswordReset={sendPasswordReset}
        onConfirmPasswordReset={resetPassword}
        onClearPasswordResetToken={clearPasswordResetToken}
        onResendEmailVerification={resendVerification}
        onLogout={logout}
        onSaveSettings={saveNotificationSettings}
        onSendTestEmail={testEmailNotification}
      />

      {error ? (
        <section className="error-banner" role="alert">
          <div><strong>数据暂时无法更新</strong><span>{error}</span></div>
          <button type="button" onClick={() => void loadMarkets()}>重新加载</button>
        </section>
      ) : null}

      {activeAlerts.length > 0 ? (
        <section className={`alert-banner ${activeAlerts[0].severity}`} role="alert">
          <div>
            <span>{activeAlerts.length} 条风险事件待确认</span>
            <strong>{activeAlerts[0].title}</strong>
            <p>{activeAlerts[0].message}</p>
          </div>
          <a href="#alerts">查看预警中心</a>
        </section>
      ) : null}

      <section className="market-grid" aria-label="核心资产行情">
        {loadingMarkets && markets.length === 0
          ? [0, 1, 2, 3].map((item) => <div className="market-card skeleton-card" key={item} />)
          : markets.map((coin) => (
              <MarketCard
                key={coin.id}
                coin={coin}
                active={coin.id === selectedId}
                onSelect={setSelectedId}
              />
            ))}
      </section>

      <section className="dashboard-grid">
        <div className="panel chart-panel">
          <div className="panel-header">
            <div>
              <span className="panel-eyebrow">MULTI-TIMEFRAME CANDLESTICK</span>
              <h2>{selectedId === "gold" ? "黄金 K线图" : `${selectedCoin?.name ?? "市场"} K线图`}</h2>
            </div>
            {selectedCoin && displayedPanelPrice !== undefined ? (
              <div className="current-quote">
                <strong>{priceCurrency.format(displayedPanelPrice)}</strong>
                <span>{selectedChartQuote
                  ? `${selectedChartQuote.displaySymbol} K线最新价${selectedChartQuote.isProxy ? "（实时代理）" : "（延迟历史）"}`
                  : selectedId === "gold" ? "XAU/USD 当前参考价" : `${selectedCoin.symbol} / USD`}</span>
                <button
                  className={`watch-button ${watchlist.includes(selectedCoin.id) ? "saved" : ""}`}
                  type="button"
                  onClick={() => void toggleWatchlist()}
                  disabled={watchlistBusy}
                >
                  {!user ? "登录后加入自选" : watchlist.includes(selectedCoin.id) ? "★ 已加入自选" : "☆ 加入自选"}
                </button>
              </div>
            ) : null}
          </div>
          <ChartErrorBoundary resetKey={selectedId}>
            <CandlestickChart
              assetId={selectedId}
              symbol={selectedCoin?.symbol ?? "Asset"}
              onLatestQuoteChange={setChartQuote}
            />
          </ChartErrorBoundary>
        </div>
        <RiskPanel risk={risk} loading={loadingDetail} unavailable={selectedId === "gold"} />
      </section>

      <DerivativesPanel
        snapshot={risk?.market_context ?? null}
        liquidation={liquidationStats}
        unavailable={selectedId === "gold"}
      />

      <RiskBacktestPanel
        backtest={riskBacktest}
        loading={backtestLoading}
        error={backtestError}
        unavailable={selectedId === "gold"}
      />

      <AlertCenter
        authenticated={Boolean(user)}
        rules={alertRules}
        events={alertEvents}
        busy={alertsBusy}
        onCreate={createRule}
        onDelete={deleteRule}
        onAcknowledge={acknowledgeEvent}
        onEvaluate={checkAlerts}
      />

      <NewsPanel news={news} loading={loadingDetail} />

      <section className="methodology">
        <p className="kicker">HOW THE SCORE WORKS</p>
        <h2>风险评分不是黑箱</h2>
        <div className="method-grid">
          <article><span>01</span><h3>价格波动</h3><p>衡量日收益率离散程度，识别市场是否进入不稳定阶段。</p></article>
          <article><span>02</span><h3>最大回撤</h3><p>计算观察期内从高点到低点的最大跌幅，反映下行风险。</p></article>
          <article><span>03</span><h3>成交异常</h3><p>将最新成交量与近期均值比较，发现市场活跃度突然变化。</p></article>
          <article><span>04</span><h3>短期动量</h3><p>监测最近一期的剧烈涨跌，提示可能的追涨或抛售风险。</p></article>
          <article><span>05</span><h3>杠杆与拥挤</h3><p>综合资金费率、持仓量变化和多空比例，识别杠杆堆积及连锁强平风险。</p></article>
          <article><span>06</span><h3>市场情绪</h3><p>将恐慌贪婪指数和负面新闻占比纳入评分，观察极端情绪带来的反转风险。</p></article>
        </div>
      </section>

      <footer>
        <div><strong>ChainScope</strong><span>Web3智能市场分析与风险预警平台</span></div>
        <p>仅用于学习和市场研究，不构成投资建议。</p>
      </footer>
    </main>
  );
}
