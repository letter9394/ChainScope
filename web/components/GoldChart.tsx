"use client";

import { useEffect, useState } from "react";

import { CandlestickChart, type LatestChartQuote } from "@/components/CandlestickChart";
import { TradingViewGoldChart } from "@/components/TradingViewGoldChart";

interface GoldChartProps {
  onLatestQuoteChange?: (quote: LatestChartQuote | null) => void;
}

export function GoldChart({ onLatestQuoteChange }: GoldChartProps) {
  const [mode, setMode] = useState<"tradingview" | "native">("tradingview");

  useEffect(() => {
    if (mode === "tradingview") onLatestQuoteChange?.(null);
  }, [mode, onLatestQuoteChange]);

  return (
    <div className="gold-chart-shell">
      <div className="gold-chart-mode" aria-label="黄金图表来源">
        <div>
          <strong>黄金图表来源</strong>
          <span>{mode === "tradingview" ? "实时 XAU/USD 与完整指标" : "服务器转发备用行情"}</span>
        </div>
        <div className="gold-chart-mode-buttons">
          <button
            className={mode === "tradingview" ? "active" : ""}
            type="button"
            onClick={() => setMode("tradingview")}
          >
            TradingView 实时图
          </button>
          <button
            className={mode === "native" ? "active" : ""}
            type="button"
            onClick={() => setMode("native")}
          >
            站内备用图
          </button>
        </div>
      </div>

      {mode === "tradingview" ? (
        <TradingViewGoldChart />
      ) : (
        <CandlestickChart assetId="gold" symbol="XAU" onLatestQuoteChange={onLatestQuoteChange} />
      )}
    </div>
  );
}
