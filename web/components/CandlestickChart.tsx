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
  type MouseEventParams,
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
type IncrementalStatus = "connecting" | "live" | "retrying";
type GoldSource = "proxy" | "exact";
type LineApi = ISeriesApi<"Line">;
type HistogramApi = ISeriesApi<"Histogram">;

interface IndicatorParameters {
  ma: [number, number, number];
  bollPeriod: number;
  bollMultiplier: number;
  rsiPeriod: number;
  macdFast: number;
  macdSlow: number;
  macdSignal: number;
}

const defaultIndicatorParameters: IndicatorParameters = {
  ma: [5, 10, 20],
  bollPeriod: 20,
  bollMultiplier: 2,
  rsiPeriod: 14,
  macdFast: 12,
  macdSlow: 26,
  macdSignal: 9,
};

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

function macdData(candles: CandlePoint[], fastPeriod: number, slowPeriod: number, signalPeriod: number) {
  const closes = candles.map((item) => item.close);
  const fast = exponentialMovingAverage(closes, fastPeriod);
  const slow = exponentialMovingAverage(closes, slowPeriod);
  const values = closes.map((_, index) => fast[index] - slow[index]);
  const signalValues = exponentialMovingAverage(values, signalPeriod);
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
  const [parameters, setParameters] = useState<IndicatorParameters>(defaultIndicatorParameters);
  const [showParameters, setShowParameters] = useState(false);
  const [inspectedCandle, setInspectedCandle] = useState<CandlePoint | null>(null);
  const [incrementalStatus, setIncrementalStatus] = useState<IncrementalStatus>("connecting");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [goldSource, setGoldSource] = useState<GoldSource>("proxy");
  const shellRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<HistogramApi | null>(null);
  const indicatorRefs = useRef<IndicatorSeriesRefs>(emptyIndicatorRefs());
  const fittedKeyRef = useRef("");
  const renderedKeyRef = useRef("");
  const renderedFirstTimeRef = useRef(0);
  const renderedLastTimeRef = useRef(0);
  const renderedCountRef = useRef(0);
  const candleLookupRef = useRef<Map<number, CandlePoint>>(new Map());
  const requestGenerationRef = useRef(0);
  const incrementalInFlightRef = useRef<number | null>(null);

  const loadInitial = useCallback(async (generation: number, signal?: AbortSignal) => {
    try {
      const source = assetId === "gold" ? goldSource : undefined;
      const result = await getCandles(assetId, interval, 300, signal, source);
      if (signal?.aborted || requestGenerationRef.current !== generation) return null;
      if (result.asset_id !== assetId || result.interval !== interval || result.candles.length < 2) {
        throw new Error("K线数据不完整，请重试");
      }
      setSeries(result);
      setError(null);
      setIncrementalStatus("live");
      return result;
    } catch (reason) {
      if (!signal?.aborted && requestGenerationRef.current === generation) {
        setError(reason instanceof Error ? reason.message : "K线数据加载失败");
        setIncrementalStatus("retrying");
      }
      return null;
    } finally {
      if (!signal?.aborted && requestGenerationRef.current === generation) {
        setLoading(false);
      }
    }
  }, [assetId, goldSource, interval]);

  const loadIncremental = useCallback(async (generation: number) => {
    if (requestGenerationRef.current !== generation) return;
    if (incrementalInFlightRef.current === generation) return;
    incrementalInFlightRef.current = generation;
    try {
      const source = assetId === "gold" ? goldSource : undefined;
      const result = await getCandles(assetId, interval, 2, undefined, source);
      if (requestGenerationRef.current !== generation) return;
      setSeries((current) => {
        // An incremental response is never a valid replacement for the complete
        // series. This also prevents a late response from an old timeframe from
        // collapsing the next chart to only two candles.
        if (requestGenerationRef.current !== generation) return current;
        if (!current || current.asset_id !== assetId || current.interval !== interval) return current;
        if (result.asset_id !== assetId || result.interval !== interval) return current;
        if (current.symbol !== result.symbol || current.provider !== result.provider) return current;
        const byTime = new Map(current.candles.map((candle) => [candle.time, candle]));
        result.candles.forEach((candle) => byTime.set(candle.time, candle));
        const candles = [...byTime.values()].sort((left, right) => left.time - right.time).slice(-300);
        return { ...current, ...result, candles };
      });
      if (requestGenerationRef.current === generation) setIncrementalStatus("live");
    } catch {
      // Keep the last good chart visible while the incremental updater reconnects.
      if (requestGenerationRef.current === generation) setIncrementalStatus("retrying");
    } finally {
      if (incrementalInFlightRef.current === generation) {
        incrementalInFlightRef.current = null;
      }
    }
  }, [assetId, goldSource, interval]);

  useEffect(() => {
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    incrementalInFlightRef.current = null;
    const controller = new AbortController();
    let timer: number | undefined;
    setLoading(true);
    setError(null);
    setSeries(null);
    setInspectedCandle(null);
    setIncrementalStatus("connecting");
    renderedKeyRef.current = "";
    renderedFirstTimeRef.current = 0;
    renderedLastTimeRef.current = 0;
    renderedCountRef.current = 0;
    void loadInitial(generation, controller.signal).then((loadedSeries) => {
      if (loadedSeries && !controller.signal.aborted && requestGenerationRef.current === generation) {
        const refreshMilliseconds = assetId === "gold" && !loadedSeries.is_proxy
          ? 5 * 60_000
          : 2_000;
        timer = window.setInterval(() => void loadIncremental(generation), refreshMilliseconds);
      }
    });
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [assetId, loadIncremental, loadInitial, reloadNonce]);

  useEffect(() => {
    candleLookupRef.current = new Map((series?.candles ?? []).map((candle) => [candle.time, candle]));
  }, [series]);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === shellRef.current);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

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

    const handleCrosshairMove = (param: MouseEventParams) => {
      if (typeof param.time !== "number") {
        setInspectedCandle(null);
        return;
      }
      setInspectedCandle(candleLookupRef.current.get(param.time) ?? null);
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    const observer = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: Math.floor(entry.contentRect.width), height: Math.floor(entry.contentRect.height) });
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
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
      indicators.ma5?.setData([]);
      indicators.ma10?.setData([]);
      indicators.ma20?.setData([]);
      indicators.bollUpper?.setData([]);
      indicators.bollMiddle?.setData([]);
      indicators.bollLower?.setData([]);
      indicators.macd?.setData([]);
      indicators.macdSignal?.setData([]);
      indicators.macdHistogram?.setData([]);
      indicators.rsi?.setData([]);
      return;
    }

    const candleData = series.candles.map((item) => ({
      time: item.time as UTCTimestamp,
      open: item.open, high: item.high, low: item.low, close: item.close,
    }));
    const volumeData = series.candles.map((item) => ({
      time: item.time as UTCTimestamp, value: item.volume,
      color: item.close >= item.open ? "rgba(50, 227, 167, .42)" : "rgba(255, 95, 120, .42)",
    }));
    const maFast = simpleMovingAverage(series.candles, parameters.ma[0]);
    const maMedium = simpleMovingAverage(series.candles, parameters.ma[1]);
    const maSlow = simpleMovingAverage(series.candles, parameters.ma[2]);
    const boll = bollingerBands(series.candles, parameters.bollPeriod, parameters.bollMultiplier);
    const macd = macdData(
      series.candles,
      parameters.macdFast,
      parameters.macdSlow,
      parameters.macdSignal,
    );
    const rsi = rsiData(series.candles, parameters.rsiPeriod);
    const parameterKey = JSON.stringify(parameters);
    const renderKey = `${series.asset_id}:${series.interval}:${series.symbol}:${series.provider}:${subIndicator}:${parameterKey}`;
    const previousFirstTime = renderedFirstTimeRef.current;
    const previousLastTime = renderedLastTimeRef.current;
    const previousCount = renderedCountRef.current;
    const currentFirstTime = series.candles[0]?.time ?? 0;
    const currentLastTime = series.candles.at(-1)?.time ?? 0;
    const fullRender = (
      renderedKeyRef.current !== renderKey
      || previousLastTime === 0
      || currentLastTime < previousLastTime
      || currentFirstTime < previousFirstTime
      || series.candles.length > previousCount + 2
    );

    if (fullRender) {
      candles.setData(candleData);
      volume.setData(volumeData);
      indicators.ma5?.setData(maFast);
      indicators.ma10?.setData(maMedium);
      indicators.ma20?.setData(maSlow);
      indicators.bollUpper?.setData(boll.upper);
      indicators.bollMiddle?.setData(boll.middle);
      indicators.bollLower?.setData(boll.lower);
      indicators.macd?.setData(macd.macd);
      indicators.macdSignal?.setData(macd.signal);
      indicators.macdHistogram?.setData(macd.histogram);
      indicators.rsi?.setData(rsi);
      renderedKeyRef.current = renderKey;
    } else {
      candleData.filter((point) => Number(point.time) >= previousLastTime).forEach((point) => candles.update(point));
      volumeData.filter((point) => Number(point.time) >= previousLastTime).forEach((point) => volume.update(point));
      const updateLine = (api: LineApi | null, data: LineData<UTCTimestamp>[]) => {
        data.filter((point) => Number(point.time) >= previousLastTime).forEach((point) => api?.update(point));
      };
      const updateHistogram = (api: HistogramApi | null, data: HistogramData<UTCTimestamp>[]) => {
        data.filter((point) => Number(point.time) >= previousLastTime).forEach((point) => api?.update(point));
      };
      updateLine(indicators.ma5, maFast);
      updateLine(indicators.ma10, maMedium);
      updateLine(indicators.ma20, maSlow);
      updateLine(indicators.bollUpper, boll.upper);
      updateLine(indicators.bollMiddle, boll.middle);
      updateLine(indicators.bollLower, boll.lower);
      updateLine(indicators.macd, macd.macd);
      updateLine(indicators.macdSignal, macd.signal);
      updateHistogram(indicators.macdHistogram, macd.histogram);
      updateLine(indicators.rsi, rsi);
    }
    renderedFirstTimeRef.current = currentFirstTime;
    renderedLastTimeRef.current = currentLastTime;
    renderedCountRef.current = series.candles.length;
    chart.timeScale().applyOptions({ timeVisible: !["1d", "1w"].includes(interval) });

    const fittedKey = `${assetId}:${interval}:${series.symbol}:${series.provider}:${subIndicator}`;
    if (fittedKeyRef.current !== fittedKey) {
      const visibleBars = containerRef.current && containerRef.current.clientWidth < 600 ? 72 : 140;
      chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, series.candles.length - visibleBars), to: series.candles.length + 4,
      });
      fittedKeyRef.current = fittedKey;
    }
  }, [assetId, interval, parameters, series, showBoll, showMA, showVolume, subIndicator]);

  const updatedLabel = useMemo(() => {
    if (!series) return "等待数据";
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(new Date(series.updated_at));
  }, [series]);

  const latest = series?.candles.at(-1);
  const showingExactGold = assetId === "gold"
    && (series ? series.is_proxy === false : goldSource === "exact");
  const activeCandle = inspectedCandle ?? latest;
  const priceDigits = activeCandle && activeCandle.close < 10 ? 4 : 2;
  const activeCandleTime = activeCandle
    ? new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date(activeCandle.time * 1_000))
    : null;
  const toggleSubIndicator = (value: Exclude<SubIndicator, null>) => {
    setSubIndicator((current) => current === value ? null : value);
  };
  const setNumericParameter = (
    key: Exclude<keyof IndicatorParameters, "ma">,
    value: number,
    minimum: number,
    maximum: number,
  ) => {
    const safeValue = Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));
    setParameters((current) => ({ ...current, [key]: safeValue }));
  };
  const setMAPeriod = (index: number, value: number) => {
    const safeValue = Math.min(200, Math.max(2, Number.isFinite(value) ? value : 2));
    setParameters((current) => {
      const ma = [...current.ma] as [number, number, number];
      ma[index] = safeValue;
      return { ...current, ma };
    });
  };
  const toggleFullscreen = async () => {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await shellRef.current?.requestFullscreen();
  };

  return (
    <div className="candlestick-shell" ref={shellRef}>
      <div className="chart-toolbar">
        {assetId === "gold" ? (
          <div className="gold-source-row" aria-label="黄金K线数据模式">
            <span>数据模式</span>
            <button className={goldSource === "proxy" ? "active" : ""} type="button" onClick={() => setGoldSource("proxy")}>
              实时代理 PAXG
            </button>
            <button className={goldSource === "exact" ? "active" : ""} type="button" onClick={() => setGoldSource("exact")}>
              精确现货 XAU/USD（延迟2天）
            </button>
          </div>
        ) : null}
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
          <button className={showParameters ? "active" : ""} type="button" onClick={() => setShowParameters((value) => !value)}>参数</button>
          <button type="button" onClick={() => void toggleFullscreen()}>{isFullscreen ? "退出全屏" : "全屏"}</button>
          <span className={`incremental-status ${incrementalStatus}`}>
            {incrementalStatus === "live"
              ? showingExactGold ? "历史数据 · 延迟2天" : assetId === "gold" ? "2秒实时代理" : "2秒增量"
              : incrementalStatus === "retrying" ? "正在重连" : "正在连接"}
          </span>
        </div>
      </div>

      {showParameters ? (
        <div className="indicator-parameters" aria-label="指标参数设置">
          <label>MA 1<input type="number" min="2" max="200" value={parameters.ma[0]} onChange={(event) => setMAPeriod(0, Number(event.target.value))} /></label>
          <label>MA 2<input type="number" min="2" max="200" value={parameters.ma[1]} onChange={(event) => setMAPeriod(1, Number(event.target.value))} /></label>
          <label>MA 3<input type="number" min="2" max="200" value={parameters.ma[2]} onChange={(event) => setMAPeriod(2, Number(event.target.value))} /></label>
          <label>BOLL周期<input type="number" min="5" max="100" value={parameters.bollPeriod} onChange={(event) => setNumericParameter("bollPeriod", Number(event.target.value), 5, 100)} /></label>
          <label>BOLL倍数<input type="number" min="1" max="5" step="0.1" value={parameters.bollMultiplier} onChange={(event) => setNumericParameter("bollMultiplier", Number(event.target.value), 1, 5)} /></label>
          <label>RSI周期<input type="number" min="2" max="100" value={parameters.rsiPeriod} onChange={(event) => setNumericParameter("rsiPeriod", Number(event.target.value), 2, 100)} /></label>
          <label>MACD快线<input type="number" min="2" max="100" value={parameters.macdFast} onChange={(event) => setNumericParameter("macdFast", Number(event.target.value), 2, 100)} /></label>
          <label>MACD慢线<input type="number" min="3" max="200" value={parameters.macdSlow} onChange={(event) => setNumericParameter("macdSlow", Number(event.target.value), 3, 200)} /></label>
          <label>MACD信号<input type="number" min="2" max="100" value={parameters.macdSignal} onChange={(event) => setNumericParameter("macdSignal", Number(event.target.value), 2, 100)} /></label>
          <button type="button" onClick={() => setParameters(defaultIndicatorParameters)}>恢复默认</button>
        </div>
      ) : null}

      <div className="native-chart-meta">
        <div>
          <strong>{series?.display_symbol ?? (assetId === "gold" ? "XAU/USD" : `${symbol}/USDT`)}</strong>
          <span>{series?.provider ?? "Binance Spot"} · 服务器转发</span>
        </div>
        <span>更新于 {updatedLabel}</span>
      </div>

      {activeCandle ? (
        <div className="ohlc-strip" aria-label="当前K线价格">
          <span className="ohlc-time">{inspectedCandle ? "十字光标" : "最新"} · {activeCandleTime}</span>
          <span>开 <strong>{activeCandle.open.toFixed(priceDigits)}</strong></span>
          <span>高 <strong className="price-up">{activeCandle.high.toFixed(priceDigits)}</strong></span>
          <span>低 <strong className="price-down">{activeCandle.low.toFixed(priceDigits)}</strong></span>
          <span>收 <strong>{activeCandle.close.toFixed(priceDigits)}</strong></span>
          <span>量 <strong>{new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 }).format(activeCandle.volume)}</strong></span>
        </div>
      ) : null}

      <div className="indicator-legend" aria-label="指标图例">
        {showMA ? <><span className="ma5">MA{parameters.ma[0]}</span><span className="ma10">MA{parameters.ma[1]}</span><span className="ma20">MA{parameters.ma[2]}</span></> : null}
        {showBoll ? <span className="boll">BOLL({parameters.bollPeriod},{parameters.bollMultiplier})</span> : null}
        {subIndicator === "MACD" ? <><span className="dif">DIF</span><span className="dea">DEA</span></> : null}
        {subIndicator === "RSI" ? <span className="rsi">RSI({parameters.rsiPeriod})</span> : null}
      </div>

      {assetId === "gold" ? (
        <div className="proxy-notice" role="note">
          <strong>{showingExactGold ? "XAU/USD 精确历史行情" : "PAXG 实时黄金代理行情"}</strong>
          <span>{series?.proxy_notice ?? (showingExactGold
            ? "现货 XAU/USD 聚合报价；Massive 免费方案延迟 2 天，不会随当前价格实时跳动。"
            : "当前 K 线使用 PAXG/USDT 实时代理黄金走势；它接近但不等同于现货 XAU/USD。")}</span>
        </div>
      ) : null}

      <div className="native-chart" aria-label={`${symbol} 站内K线图`}>
        <div ref={containerRef} className="native-chart-canvas" />
        {loading ? <div className="chart-state">正在加载 {interval} K线…</div> : null}
        {error ? (
          <div className="chart-state chart-state-error">
            <span>{error}</span>
            <button type="button" onClick={() => setReloadNonce((value) => value + 1)}>重试</button>
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
