"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import { getCandles } from "@/lib/api";
import type { CandleInterval, CandleSeries as CandleSeriesResponse } from "@/lib/types";

const intervals: Array<{ value: CandleInterval; label: string }> = [
  { value: "1m", label: "1分" },
  { value: "5m", label: "5分" },
  { value: "15m", label: "15分" },
  { value: "30m", label: "30分" },
  { value: "1h", label: "1小时" },
  { value: "4h", label: "4小时" },
  { value: "1d", label: "日线" },
  { value: "1w", label: "周线" },
];

interface CandlestickChartProps {
  assetId: string;
  symbol: string;
}

export function CandlestickChart({ assetId, symbol }: CandlestickChartProps) {
  const [interval, setIntervalValue] = useState<CandleInterval>("15m");
  const [series, setSeries] = useState<CandleSeriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const fittedKeyRef = useRef("");

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getCandles(assetId, interval, 300, signal);
      setSeries(result);
      setError(null);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(reason instanceof Error ? reason.message : "K线数据加载失败");
      }
    } finally {
      setLoading(false);
    }
  }, [assetId, interval]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setSeries(null);
    void load(controller.signal);
    const timer = window.setInterval(() => void load(), 10_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#0d1916" },
        textColor: "#91aaa1",
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "rgba(185, 232, 215, 0.06)" },
        horzLines: { color: "rgba(185, 232, 215, 0.06)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: "rgba(185, 232, 215, 0.14)",
        scaleMargins: { top: 0.08, bottom: 0.25 },
      },
      timeScale: {
        borderColor: "rgba(185, 232, 215, 0.14)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 3,
      },
      localization: { locale: "zh-CN" },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#65e6be",
      downColor: "#ff7c8c",
      borderUpColor: "#65e6be",
      borderDownColor: "#ff7c8c",
      wickUpColor: "#65e6be",
      wickDownColor: "#ff7c8c",
      priceLineColor: "rgba(101, 230, 190, 0.58)",
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      borderVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volumeSeriesRef.current = volume;

    const observer = new ResizeObserver(([entry]) => {
      chart.applyOptions({
        width: Math.floor(entry.contentRect.width),
        height: Math.floor(entry.contentRect.height),
      });
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    if (!chart || !candles || !volume) return;
    if (!series) {
      candles.setData([]);
      volume.setData([]);
      return;
    }

    candles.setData(series.candles.map((item) => ({
      time: item.time as UTCTimestamp,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    })));
    volume.setData(series.candles.map((item) => ({
      time: item.time as UTCTimestamp,
      value: item.volume,
      color: item.close >= item.open ? "rgba(101, 230, 190, 0.34)" : "rgba(255, 124, 140, 0.34)",
    })));
    chart.timeScale().applyOptions({ timeVisible: !["1d", "1w"].includes(interval) });

    const fittedKey = `${assetId}:${interval}`;
    if (fittedKeyRef.current !== fittedKey) {
      chart.timeScale().fitContent();
      fittedKeyRef.current = fittedKey;
    }
  }, [assetId, interval, series]);

  const updatedLabel = useMemo(() => {
    if (!series) return "等待数据";
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(series.updated_at));
  }, [series]);

  return (
    <div className="candlestick-shell">
      <div className="timeframe-row" aria-label={`${symbol} K线周期`}>
        {intervals.map((item) => (
          <button
            className={interval === item.value ? "active" : ""}
            type="button"
            key={item.value}
            onClick={() => setIntervalValue(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="native-chart-meta">
        <div>
          <strong>{series?.display_symbol ?? (assetId === "gold" ? "PAXG/USDT" : `${symbol}/USDT`)}</strong>
          <span>{series?.provider ?? "Binance Spot"} · 服务器转发</span>
        </div>
        <span>更新于 {updatedLabel}</span>
      </div>

      {assetId === "gold" ? (
        <div className="proxy-notice" role="note">
          <strong>PAXG 黄金代理行情</strong>
          <span>{series?.proxy_notice ?? "当前 K 线使用 PAXG/USDT 作为 XAU 走势代理，不等同于现货 XAU/USD。"}</span>
        </div>
      ) : null}

      <div className="native-chart" aria-label={`${symbol} 站内K线图`}>
        <div ref={containerRef} className="native-chart-canvas" />
        {loading ? <div className="chart-state">正在加载 {interval} K线…</div> : null}
        {error ? (
          <div className="chart-state chart-state-error">
            <span>{error}</span>
            <button type="button" onClick={() => { setLoading(true); void load(); }}>重试</button>
          </div>
        ) : null}
      </div>

      <p className="chart-credit">
        行情由 Binance Spot 提供并经 ChainScope 服务器缓存转发；图表使用
        {" "}<a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a>。
      </p>
    </div>
  );
}
