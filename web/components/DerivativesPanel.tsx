import type { LiquidationStats } from "@/hooks/useLiquidationStream";
import type { DerivativesSnapshot } from "@/lib/types";

interface DerivativesPanelProps {
  snapshot: DerivativesSnapshot | null;
  liquidation: LiquidationStats;
  unavailable?: boolean;
}

const compactUsd = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 2,
});

const percent = (value: number | null, digits = 2) => value === null ? "暂不可用" : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;

export function DerivativesPanel({ snapshot, liquidation, unavailable = false }: DerivativesPanelProps) {
  if (unavailable) {
    return (
      <section className="derivatives-section panel">
        <div><p className="kicker">REAL-TIME DERIVATIVES</p><h2>实时衍生品风险</h2></div>
        <p className="derivatives-unavailable">XAU 是现货黄金，不适用加密永续合约资金费率、持仓量和强平指标。</p>
      </section>
    );
  }

  const liquidationLabel = liquidation.status === "live"
    ? liquidation.totalUsd > 0 ? compactUsd.format(liquidation.totalUsd) : "监听中 · 暂无事件"
    : liquidation.status === "connecting" ? "正在连接…" : "连接中断，自动重试";

  return (
    <section className="derivatives-section panel">
      <div className="derivatives-heading">
        <div><p className="kicker">REAL-TIME DERIVATIVES</p><h2>实时衍生品风险</h2></div>
        <span className={`derivatives-live ${snapshot?.available ? "live" : ""}`}><i /> {snapshot?.available ? "每10秒更新" : "数据暂不可用"}</span>
      </div>
      <div className="derivatives-grid">
        <article><span>资金费率 / 8H</span><strong>{percent(snapshot?.funding_rate_percent ?? null, 4)}</strong><small>年化估算 {percent(snapshot?.annualized_funding_percent ?? null)}</small></article>
        <article><span>未平仓合约价值</span><strong>{snapshot?.open_interest_usd ? compactUsd.format(snapshot.open_interest_usd) : "暂不可用"}</strong><small>5分钟变化 {percent(snapshot?.open_interest_change_5m_percent ?? null)}</small></article>
        <article><span>多空账户比例</span><strong>{snapshot?.long_short_ratio?.toFixed(2) ?? "暂不可用"}</strong><small>多 {snapshot?.long_account_percent?.toFixed(1) ?? "—"}% · 空 {snapshot?.short_account_percent?.toFixed(1) ?? "—"}%</small></article>
        <article><span>恐慌与贪婪</span><strong>{snapshot?.fear_greed_value ?? "—"}</strong><small>{snapshot?.fear_greed_label ?? "全市场情绪暂不可用"}</small></article>
        <article className="liquidation-card"><span>近5分钟实时强平</span><strong>{liquidationLabel}</strong><small>多单 {compactUsd.format(liquidation.longUsd)} · 空单 {compactUsd.format(liquidation.shortUsd)}</small></article>
      </div>
      <p className="derivatives-note">资金费率、持仓量和多空比来自 Binance U本位永续合约；强平数据从页面打开后实时累计，不伪造历史值。极端值会计入复合风险分。</p>
    </section>
  );
}
