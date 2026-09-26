"use client";

import { useMemo, useState } from "react";

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

const tradingViewSymbol = "OANDA:XAUUSD";

export function TradingViewGoldChart() {
  const [interval, setIntervalValue] = useState("15");
  const chartUrl = useMemo(() => {
    const config = {
      autosize: true,
      symbol: tradingViewSymbol,
      interval,
      timezone: "Asia/Shanghai",
      theme: "dark",
      style: "1",
      locale: "zh_CN",
      backgroundColor: "#081411",
      gridColor: "rgba(185, 232, 215, 0.08)",
      hide_top_toolbar: false,
      hide_side_toolbar: false,
      hide_legend: false,
      hide_volume: false,
      allow_symbol_change: false,
      save_image: true,
      calendar: false,
      withdateranges: true,
      support_host: "https://www.tradingview.com",
      width: "100%",
      height: "100%",
    };
    return `https://www.tradingview-widget.com/embed-widget/advanced-chart/?locale=zh_CN#${encodeURIComponent(JSON.stringify(config))}`;
  }, [interval]);

  return (
    <div className="tradingview-gold-shell">
      <div className="timeframe-row" aria-label="XAU/USD TradingView K线周期">
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
          title="XAU/USD TradingView 实时K线图"
          src={chartUrl}
          loading="eager"
          allow="clipboard-write; fullscreen"
          allowFullScreen
          referrerPolicy="origin"
        />
      </div>
      <div className="tradingview-footer">
        <span>OANDA:XAUUSD · TradingView 实时图表与技术指标</span>
        <a
          href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tradingViewSymbol)}`}
          target="_blank"
          rel="noreferrer"
        >
          在 TradingView 打开 ↗
        </a>
      </div>
    </div>
  );
}
