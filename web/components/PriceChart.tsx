import type { HistoryPoint } from "@/lib/types";

interface PriceChartProps {
  history: HistoryPoint[];
  symbol: string;
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

export function PriceChart({ history, symbol }: PriceChartProps) {
  if (history.length < 2) {
    return <div className="chart-empty">历史数据不足</div>;
  }

  const width = 900;
  const height = 310;
  const inset = 18;
  const prices = history.map((point) => point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const coordinates = history.map((point, index) => {
    const x = inset + (index / (history.length - 1)) * (width - inset * 2);
    const y = inset + ((max - point.price) / range) * (height - inset * 2);
    return { x, y, point };
  });
  const linePath = coordinates
    .map(({ x, y }, index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L ${coordinates.at(-1)?.x} ${height - inset} L ${inset} ${height - inset} Z`;
  const positive = prices.at(-1)! >= prices[0];

  return (
    <div className="chart-wrap">
      <div className="chart-scale" aria-hidden="true">
        <span>${formatCompact(max)}</span>
        <span>${formatCompact((max + min) / 2)}</span>
        <span>${formatCompact(min)}</span>
      </div>
      <svg
        className="price-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${symbol} 30天价格曲线`}
      >
        <defs>
          <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={positive ? "#65e6be" : "#ff7c8c"} stopOpacity="0.28" />
            <stop offset="100%" stopColor={positive ? "#65e6be" : "#ff7c8c"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line
            key={ratio}
            x1={inset}
            x2={width - inset}
            y1={height * ratio}
            y2={height * ratio}
            stroke="rgba(255,255,255,0.08)"
            strokeDasharray="5 8"
          />
        ))}
        <path d={areaPath} fill="url(#areaGradient)" />
        <path
          d={linePath}
          fill="none"
          stroke={positive ? "#65e6be" : "#ff7c8c"}
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="chart-dates">
        <span>{new Date(history[0].timestamp).toLocaleDateString("zh-CN")}</span>
        <span>{new Date(history.at(-1)!.timestamp).toLocaleDateString("zh-CN")}</span>
      </div>
    </div>
  );
}
