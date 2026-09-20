import type { RiskAssessment } from "@/lib/types";

interface RiskPanelProps {
  risk: RiskAssessment | null;
  loading: boolean;
  unavailable?: boolean;
}

export function RiskPanel({ risk, loading, unavailable = false }: RiskPanelProps) {
  if (unavailable) {
    return (
      <aside className="panel risk-panel asset-note-panel">
        <div className="panel-eyebrow">GOLD MARKET CONTEXT</div>
        <h3>XAU 现货黄金</h3>
        <p>黄金与加密资产的数据结构不同，当前不套用加密货币风险评分。请结合 K 线周期、美元走势、利率和宏观事件观察。</p>
        <div className="model-note"><span>报价单位</span><strong>USD / 金衡盎司</strong></div>
      </aside>
    );
  }
  if (loading || !risk) {
    return <div className="panel risk-panel skeleton-panel">正在计算风险指标…</div>;
  }

  return (
    <aside className="panel risk-panel">
      <div className="panel-eyebrow">EXPLAINABLE RISK</div>
      <div className="risk-overview">
        <div className={`risk-score ${risk.level}`}>
          <span>{risk.score}</span>
          <small>/ 100</small>
        </div>
        <div>
          <span className={`risk-badge ${risk.level}`}>{risk.level_label}风险</span>
          <p>{risk.summary}</p>
        </div>
      </div>
      <div className="metric-list">
        {risk.metrics.map((metric) => (
          <div className="metric" key={metric.key}>
            <div className="metric-heading">
              <span>{metric.label}</span>
              <strong>{metric.display_value}</strong>
            </div>
            <div className="metric-bar">
              <span style={{ width: `${Math.min(100, metric.contribution * 2.5)}%` }} />
            </div>
            <p>{metric.explanation}</p>
          </div>
        ))}
      </div>
      <div className="model-note">
        <span>规则模型 v0.1</span>
        <span>{risk.sample_days} 个日样本</span>
      </div>
    </aside>
  );
}
