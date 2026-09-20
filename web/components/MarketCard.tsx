import type { MarketCoin } from "@/lib/types";

interface MarketCardProps {
  coin: MarketCoin;
  active: boolean;
  onSelect: (coinId: string) => void;
}

const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 2,
});

const priceCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

export function MarketCard({ coin, active, onSelect }: MarketCardProps) {
  const change = coin.price_change_percentage_24h ?? 0;
  const positive = change >= 0;

  return (
    <button
      className={`market-card ${active ? "active" : ""}`}
      onClick={() => onSelect(coin.id)}
      type="button"
      aria-pressed={active}
    >
      <div className="coin-heading">
        {coin.image ? (
          <img src={coin.image} alt="" width={38} height={38} />
        ) : (
          <span className="asset-fallback">Au</span>
        )}
        <div>
          <strong>{coin.symbol}</strong>
          <span>{coin.name}</span>
        </div>
        {coin.price_change_percentage_24h == null ? (
          <span className="change spot">现货</span>
        ) : (
          <span className={`change ${positive ? "positive" : "negative"}`}>
            {positive ? "+" : ""}{change.toFixed(2)}%
          </span>
        )}
      </div>
      <div className="coin-price">{priceCurrency.format(coin.current_price)}</div>
      <div className="coin-meta">
        <span>{coin.id === "gold" ? "美元 / 金衡盎司" : `市值 ${coin.market_cap ? compactCurrency.format(coin.market_cap) : "—"}`}</span>
        <span>{coin.id === "gold" ? "XAU/USD" : "24h"}</span>
      </div>
    </button>
  );
}
