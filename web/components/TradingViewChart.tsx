"use client";

import { useMemo, useState } from "react";

const tradingViewSymbols: Record<string, string> = {
  bitcoin: "BINANCE:BTCUSDT",
  ethereum: "BINANCE:ETHUSDT",
  solana: "BINANCE:SOLUSDT",
  gold: "OANDA:XAUUSD",
};

const intervals = [
  { value: "1", label: "1分" },
  { value: "5", label: "5分" },
  { value: "15", label: "15分" },
  { value: "30", label: "30分" },
  { value: "60", label: "1小时" },
  { value: "240", label: "4小时" },
  { value: "D", label: "日线" },
  { value: "W", label: "周线" },
] as const;

interface TradingViewChartProps {
  assetId: string;
  symbol: string;
}

export function TradingViewChart({ assetId, symbol }: TradingViewChartProps) {
  const [interval, setIntervalValue] = useState("15");
  const tradingViewSymbol = tradingViewSymbols[assetId] ?? tradingViewSymbols.bitcoin;
  const chartUrl = useMemo(() => {
    const config = {
      autosize: true,
      symbol: tradingViewSymbol,
      interval,
      timezone: "Asia/Shanghai",
      theme: "dark",
      style: "1",
      locale: "zh_CN",
      backgroundColor: "#0d1916",
      gridColor: "rgba(185, 232, 215, 0.07)",
      hide_top_toolbar: false,
      hide_side_toolbar: false,
      hide_legend: false,
      hide_volume: false,
      allow_symbol_change: false,
      save_image: false,
      calendar: false,
      withdateranges: true,
      support_host: "https://www.tradingview.com",
      width: "100%",
      height: "100%",
    };
    return `https://www.tradingview-widget.com/embed-widget/advanced-chart/?locale=zh_CN#${encodeURIComponent(JSON.stringify(config))}`;
  }, [interval, tradingViewSymbol]);

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
      <div className="tradingview-chart">
        <iframe
          key={`${tradingViewSymbol}-${interval}`}
          title={`${symbol} TradingView K线图`}
          src={chartUrl}
          loading="eager"
          allowFullScreen
        />
      </div>
      <p className="tradingview-credit">
        K线与报价由 <a href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tradingViewSymbol)}`} target="_blank" rel="noreferrer">TradingView</a> 提供
      </p>
    </div>
  );
}
