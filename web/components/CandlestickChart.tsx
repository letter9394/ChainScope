"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";

import { getCandles } from "@/lib/api";
import type { CandleInterval, CandlePoint, CandleSeries as CandleSeriesResponse } from "@/lib/types";

const intervals: Array<{ value: CandleInterval; label: string }> = [
  { value: "1m", label: "1分" }, { value: "5m", label: "5分" },
  { value: "15m", label: "15分" }, { value: "30m", label: "30分" },
  { value: "1h", label: "1小时" }, { value: "4h", label: "4小时" },
  { value: "1d", label: "日线" }, { value: "1w", label: "周线" },
];

type SubIndicator = "MACD" | "RSI" | null;
type LineApi = ISeriesApi<"Line">;
type HistogramApi = ISeriesApi<"Histogram">;

interface IndicatorSeriesRefs {
  ma5: LineApi | null;
  ma10: LineApi | null;
  ma20: LineApi | null;
  bollUpper: LineApi | null;
  bollMiddle: LineApi | null;
  bollLower: LineApi | null;
  macd: LineApi | null;
  macdSignal: LineApi | null;
  macdHistogram: HistogramApi | null;
  rsi: LineApi | null;
}

interface CandlestickChartProps {
  assetId: string;
  symbol: string;
}

const emptyIndicatorRefs = (): IndicatorSeriesRefs => ({
  ma5: null, ma10: null, ma20: null,
  bollUpper: null, bollMiddle: null, bollLower: null,
  macd: null, macdSignal: null, macdHistogram: null, rsi: null,
});

function simpleMovingAverage(candles: CandlePoint[], period: number): LineData<UTCTimestamp>[] {
  const points: LineData<UTCTimestamp>[] = [];
  let sum = 0;
  candles.forEach((candle, index) => {
    sum += candle.close;
    if (index >= period) sum -= candles[index - period].close;
    if (index >= period - 1) points.push({ time: candle.time as UTCTimestamp, value: sum / period });
  });
  return points;
}

function exponentialMovingAverage(values: number[], period: number): number[] {
  if (values.length === 0) return [];
  const multiplier = 2 / (period + 1);
  const result = [values[0]];
  for (let index = 1; index < values.length; index += 1) {
    result.push((values[index] - result[index - 1]) * multiplier + result[index - 1]);
  }
  return result;
}

function bollingerBands(candles: CandlePoint[], period = 20, multiplier = 2) {
  const upper: LineData<UTCTimestamp>[] = [];
  const middle: LineData<UTCTimestamp>[] = [];
  const lower: LineData<UTCTimestamp>[] = [];
  for (let index = period - 1; index < candles.length; index += 1) {
    const values = candles.slice(index - period + 1, index + 1).map((item) => item.close);
    const mean = values.reduce((sum, value) => sum + value, 0) / period;
    const deviation = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / period);
    const time = candles[index].time as UTCTimestamp;
    middle.push({ time, value: mean });
    upper.push({ time, value: mean + multiplier * deviation });
    lower.push({ time, value: mean - multiplier * deviation });
  }
  return { upper, middle, lower };
}

function macdData(candles: CandlePoint[]) {
  const closes = candles.map((item) => item.close);
  const fast = exponentialMovingAverage(closes, 12);
  const slow = exponentialMovingAverage(closes, 26);
  const values = closes.map((_, index) => fast[index] - slow[index]);
  const signalValues = exponentialMovingAverage(values, 9);
  const macd: LineData<UTCTimestamp>[] = [];
  const signal: LineData<UTCTimestamp>[] = [];
  const histogram: HistogramData<UTCTimestamp>[] = [];
  candles.forEach((candle, index) => {
    const time = candle.time as UTCTimestamp;
    macd.push({ time, value: values[index] });
    signal.push({ time, value: signalValues[index] });
    histogram.push({
      time,
      value: values[index] - signalValues[index],
      color: values[index] >= signalValues[index]
        ? "rgba(50, 227, 167, .58)" : "rgba(255, 95, 120, .58)",
    });
  });
  return { macd, signal, histogram };
}

function rsiData(candles: CandlePoint[], period = 14): LineData<UTCTimestamp>[] {
  if (candles.length <= period) return [];
  let gains = 0;
  let losses = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    gains += Math.max(change, 0);
    losses += Math.max(-change, 0);
  }
  let averageGain = gains / period;
  let averageLoss = losses / period;
  const points: LineData<UTCTimestamp>[] = [];
  const addPoint = (index: number) => {
    const value = averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss);
    points.push({ time: candles[index].time as UTCTimestamp, value });
  };
  addPoint(period);
  for (let index = period + 1; index < candles.length; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period;
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period;
    addPoint(index);
  }
  return points;
}

export function CandlestickChart({ assetId, symbol }: CandlestickChartProps) {
  const [interval, setIntervalValue] = useState<CandleInterval>("15m");
  const [series, setSeries] = useState<CandleSeriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showMA, setShowMA] = useState(true);
  const [showBoll, setShowBoll] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [subIndicator, setSubIndicator] = useState<SubIndicator>("MACD");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<HistogramApi | null>(null);
  const indicatorRefs = useRef<IndicatorSeriesRefs>(emptyIndicatorRefs());
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
        background: { type: ColorType.Solid, color: "#081411" },
        textColor: "#a8bdb6",
        attributionLogo: true,
        panes: {
          separatorColor: "rgba(185, 232, 215, .14)",
          separatorHoverColor: "rgba(101, 230, 190, .35)",
        },
      },
      grid: {
        vertLines: { color: "rgba(185, 232, 215, 0.08)" },
        horzLines: { color: "rgba(185, 232, 215, 0.08)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: "rgba(185, 232, 215, 0.22)",
        scaleMargins: { top: 0.08, bottom: 0.22 },
        minimumWidth: 66,
      },
      timeScale: {
        borderColor: "rgba(185, 232, 215, 0.22)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 8,
        minBarSpacing: 3,
      },
      handleScroll: true,
      handleScale: true,
      localization: { locale: "zh-CN" },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#32e3a7", downColor: "#ff5f78",
      borderUpColor: "#32e3a7", borderDownColor: "#ff5f78",
      wickUpColor: "#8df5d2", wickDownColor: "#ff9aa8",
      priceLineColor: "rgba(101, 230, 190, .72)", priceLineWidth: 2,
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "volume",
      priceLineVisible: false, lastValueVisible: false,
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.83, bottom: 0 }, borderVisible: false,
    });

    const indicators = emptyIndicatorRefs();
    indicators.ma5 = chart.addSeries(LineSeries, { color: "#ffd166", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    indicators.ma10 = chart.addSeries(LineSeries, { color: "#54a7ff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    indicators.ma20 = chart.addSeries(LineSeries, { color: "#c98cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    indicators.bollUpper = chart.addSeries(LineSeries, { color: "rgba(255, 198, 108, .82)", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    indicators.bollMiddle = chart.addSeries(LineSeries, { color: "rgba(255, 255, 255, .58)", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    indicators.bollLower = chart.addSeries(LineSeries, { color: "rgba(255, 198, 108, .82)", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });

    if (subIndicator === "MACD") {
      indicators.macdHistogram = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 1);
      indicators.macd = chart.addSeries(LineSeries, { color: "#54d8ff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }, 1);
      indicators.macdSignal = chart.addSeries(LineSeries, { color: "#ffd166", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }, 1);
    }
    if (subIndicator === "RSI") {
      indicators.rsi = chart.addSeries(LineSeries, { color: "#c98cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: true }, 1);
      indicators.rsi.createPriceLine({ price: 70, color: "rgba(255, 95, 120, .55)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "超买" });
      indicators.rsi.createPriceLine({ price: 30, color: "rgba(50, 227, 167, .55)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "超卖" });
    }
    if (subIndicator) {
      const panes = chart.panes();
      panes[0]?.setStretchFactor(3.6);
      panes[1]?.setStretchFactor(1.2);
    }

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volumeSeriesRef.current = volume;
    indicatorRefs.current = indicators;

    const observer = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: Math.floor(entry.contentRect.width), height: Math.floor(entry.contentRect.height) });
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      indicatorRefs.current = emptyIndicatorRefs();
    };
  }, [subIndicator]);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    const indicators = indicatorRefs.current;
    if (!chart || !candles || !volume) return;

    indicators.ma5?.applyOptions({ visible: showMA });
    indicators.ma10?.applyOptions({ visible: showMA });
    indicators.ma20?.applyOptions({ visible: showMA });
    indicators.bollUpper?.applyOptions({ visible: showBoll });
    indicators.bollMiddle?.applyOptions({ visible: showBoll });
    indicators.bollLower?.applyOptions({ visible: showBoll });
    volume.applyOptions({ visible: showVolume });

    if (!series) {
      candles.setData([]);
      volume.setData([]);
      return;
    }

    candles.setData(series.candles.map((item) => ({
      time: item.time as UTCTimestamp,
      open: item.open, high: item.high, low: item.low, close: item.close,
    })));
    volume.setData(series.candles.map((item) => ({
      time: item.time as UTCTimestamp, value: item.volume,
      color: item.close >= item.open ? "rgba(50, 227, 167, .42)" : "rgba(255, 95, 120, .42)",
    })));
    indicators.ma5?.setData(simpleMovingAverage(series.candles, 5));
    indicators.ma10?.setData(simpleMovingAverage(series.candles, 10));
    indicators.ma20?.setData(simpleMovingAverage(series.candles, 20));
    const boll = bollingerBands(series.candles);
    indicators.bollUpper?.setData(boll.upper);
    indicators.bollMiddle?.setData(boll.middle);
    indicators.bollLower?.setData(boll.lower);
    const macd = macdData(series.candles);
    indicators.macd?.setData(macd.macd);
    indicators.macdSignal?.setData(macd.signal);
    indicators.macdHistogram?.setData(macd.histogram);
    indicators.rsi?.setData(rsiData(series.candles));
    chart.timeScale().applyOptions({ timeVisible: !["1d", "1w"].includes(interval) });

    const fittedKey = `${assetId}:${interval}:${subIndicator}`;
    if (fittedKeyRef.current !== fittedKey) {
      const visibleBars = containerRef.current && containerRef.current.clientWidth < 600 ? 72 : 140;
      chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, series.candles.length - visibleBars), to: series.candles.length + 4,
      });
      fittedKeyRef.current = fittedKey;
    }
  }, [assetId, interval, series, showBoll, showMA, showVolume, subIndicator]);

  const updatedLabel = useMemo(() => {
    if (!series) return "等待数据";
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(new Date(series.updated_at));
  }, [series]);

  const latest = series?.candles.at(-1);
  const priceDigits = latest && latest.close < 10 ? 4 : 2;
  const toggleSubIndicator = (value: Exclude<SubIndicator, null>) => {
    setSubIndicator((current) => current === value ? null : value);
  };

  return (
    <div className="candlestick-shell">
      <div className="chart-toolbar">
        <div className="timeframe-row" aria-label={`${symbol} K线周期`}>
          {intervals.map((item) => (
            <button className={interval === item.value ? "active" : ""} type="button" key={item.value} onClick={() => setIntervalValue(item.value)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="indicator-row" aria-label="技术指标">
          <span>指标</span>
          <button className={showMA ? "active" : ""} type="button" onClick={() => setShowMA((value) => !value)}>MA</button>
          <button className={showBoll ? "active" : ""} type="button" onClick={() => setShowBoll((value) => !value)}>BOLL</button>
          <button className={subIndicator === "MACD" ? "active" : ""} type="button" onClick={() => toggleSubIndicator("MACD")}>MACD</button>
          <button className={subIndicator === "RSI" ? "active" : ""} type="button" onClick={() => toggleSubIndicator("RSI")}>RSI</button>
          <button className={showVolume ? "active" : ""} type="button" onClick={() => setShowVolume((value) => !value)}>成交量</button>
        </div>
      </div>

      <div className="native-chart-meta">
        <div>
          <strong>{series?.display_symbol ?? (assetId === "gold" ? "PAXG/USDT" : `${symbol}/USDT`)}</strong>
          <span>{series?.provider ?? "Binance Spot"} · 服务器转发</span>
        </div>
        <span>更新于 {updatedLabel}</span>
      </div>

      {latest ? (
        <div className="ohlc-strip" aria-label="当前K线价格">
          <span>开 <strong>{latest.open.toFixed(priceDigits)}</strong></span>
          <span>高 <strong className="price-up">{latest.high.toFixed(priceDigits)}</strong></span>
          <span>低 <strong className="price-down">{latest.low.toFixed(priceDigits)}</strong></span>
          <span>收 <strong>{latest.close.toFixed(priceDigits)}</strong></span>
        </div>
      ) : null}

      <div className="indicator-legend" aria-label="指标图例">
        {showMA ? <><span className="ma5">MA5</span><span className="ma10">MA10</span><span className="ma20">MA20</span></> : null}
        {showBoll ? <span className="boll">BOLL(20,2)</span> : null}
        {subIndicator === "MACD" ? <><span className="dif">DIF</span><span className="dea">DEA</span></> : null}
        {subIndicator === "RSI" ? <span className="rsi">RSI(14)</span> : null}
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

      <p className="chart-hint">拖动查看历史，滚轮或双指缩放；指标仅供学习分析，不构成交易建议。</p>
      <p className="chart-credit">
        行情由 Binance Spot 提供并经 ChainScope 服务器缓存转发；图表使用
        {" "}<a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a>。
      </p>
    </div>
  );
}
