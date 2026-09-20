"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AlertCenter } from "@/components/AlertCenter";
import { MarketCard } from "@/components/MarketCard";
import { NewsPanel } from "@/components/NewsPanel";
import { RiskPanel } from "@/components/RiskPanel";
import { TradingViewChart } from "@/components/TradingViewChart";
import {
  addToWatchlist,
  acknowledgeAlertEvent,
  createAlertRule,
  deleteAlertRule,
  evaluateAlerts,
  getAlertEvents,
  getAlertRules,
  getMarkets,
  getNews,
  getRisk,
  getWatchlist,
  removeFromWatchlist,
} from "@/lib/api";
import type {
  AlertEvent,
  AlertRule,
  AlertRuleInput,
  MarketCoin,
  NewsResponse,
  RiskAssessment,
} from "@/lib/types";

const priceCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

export default function Home() {
  const [markets, setMarkets] = useState<MarketCoin[]>([]);
  const [selectedId, setSelectedId] = useState("bitcoin");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [news, setNews] = useState<NewsResponse | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alertEvents, setAlertEvents] = useState<AlertEvent[]>([]);
  const [alertsBusy, setAlertsBusy] = useState(false);
  const [watchlistBusy, setWatchlistBusy] = useState(false);
  const [loadingMarkets, setLoadingMarkets] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedCoin = useMemo(
    () => markets.find((coin) => coin.id === selectedId) ?? markets[0],
    [markets, selectedId],
  );
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

  const checkAlerts = useCallback(async () => {
    setAlertsBusy(true);
    try {
      await evaluateAlerts();
      await loadAlertData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警检查失败");
    } finally {
      setAlertsBusy(false);
    }
  }, [loadAlertData]);

  useEffect(() => {
    const controller = new AbortController();
    void loadMarkets(controller.signal);
    void getWatchlist(controller.signal)
      .then((items) => setWatchlist(items.map((item) => item.coin_id)))
      .catch(() => setWatchlist([]));
    void checkAlerts();
    const refreshTimer = window.setInterval(() => {
      void loadMarkets();
      void checkAlerts();
    }, 60_000);
    return () => {
      controller.abort();
      window.clearInterval(refreshTimer);
    };
  }, [checkAlerts, loadMarkets]);

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

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="ChainScope 首页">
          <span className="brand-mark">CS</span>
          <span>ChainScope</span>
        </a>
        <div className="live-status"><i /> LIVE MARKET DATA</div>
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
          <span>行情来源</span><strong>CoinGecko · Gold API</strong>
          <span>K线周期</span><strong>1 分钟 — 周线</strong>
          <span>自动刷新</span><strong>60 秒</strong>
        </div>
      </section>

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
              <h2>{selectedCoin?.name ?? "市场"} K线图</h2>
            </div>
            {selectedCoin ? (
              <div className="current-quote">
                <strong>{priceCurrency.format(selectedCoin.current_price)}</strong>
                <span>{selectedCoin.symbol} / USD</span>
                <button
                  className={`watch-button ${watchlist.includes(selectedCoin.id) ? "saved" : ""}`}
                  type="button"
                  onClick={() => void toggleWatchlist()}
                  disabled={watchlistBusy}
                >
                  {watchlist.includes(selectedCoin.id) ? "★ 已加入自选" : "☆ 加入自选"}
                </button>
              </div>
            ) : null}
          </div>
          <TradingViewChart assetId={selectedId} symbol={selectedCoin?.symbol ?? "Asset"} />
        </div>
        <RiskPanel risk={risk} loading={loadingDetail} unavailable={selectedId === "gold"} />
      </section>

      <AlertCenter
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
        </div>
      </section>

      <footer>
        <div><strong>ChainScope</strong><span>Web3智能市场分析与风险预警平台</span></div>
        <p>仅用于学习和市场研究，不构成投资建议。</p>
      </footer>
    </main>
  );
}
