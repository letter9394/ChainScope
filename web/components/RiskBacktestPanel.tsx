import type { RiskBacktestResult } from "@/lib/types";

interface RiskBacktestPanelProps {
  backtest: RiskBacktestResult | null;
  loading: boolean;
  error: string | null;
  unavailable?: boolean;
}

const priceFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function RiskBacktestPanel({
  backtest,
  loading,
  error,
  unavailable = false,
}: RiskBacktestPanelProps) {
  if (unavailable) {
    return (
      <section className="panel backtest-section backtest-unavailable">
        <div className="panel-eyebrow">HISTORICAL BACKTEST</div>
        <h2>风险信号历史回测</h2>
        <p>当前回测模型针对 BTC、ETH、SOL 的加密资产日线数据；黄金需要单独构建宏观风险模型。</p>
      </section>
    );
  }

  if (loading) {
    return <section className="panel backtest-section skeleton-panel">正在回放 365 天历史风险信号…</section>;
  }

  if (error || !backtest) {
    return (
      <section className="panel backtest-section backtest-unavailable">
        <div className="panel-eyebrow">HISTORICAL BACKTEST</div>
        <h2>回测暂不可用</h2>
        <p>{error ?? "历史数据不足，请稍后重试。"}</p>
      </section>
    );
  }

  const sampleStart = dateFormatter.format(new Date(backtest.sample_start));
  const sampleEnd = dateFormatter.format(new Date(backtest.sample_end));

  return (
    <section className="panel backtest-section" id="risk-backtest">
      <div className="backtest-heading">
        <div>
          <div className="panel-eyebrow">HISTORICAL BACKTEST</div>
          <h2>{backtest.symbol} 高风险信号回测</h2>
          <p>{sampleStart}—{sampleEnd} · {backtest.model_version}</p>
        </div>
        <div className="backtest-signal-count">
          <strong>{backtest.signal_count}</strong>
          <span>次独立高风险信号</span>
        </div>
      </div>

      <div className="backtest-summary">
        <article><span>滚动窗口</span><strong>{backtest.window_days} 日</strong></article>
        <article><span>高风险阈值</span><strong>≥ {backtest.risk_threshold} 分</strong></article>
        <article><span>命中定义</span><strong>跌幅 ≥ {backtest.hit_threshold_percent}%</strong></article>
        <article><span>有效评估日</span><strong>{backtest.evaluated_points}</strong></article>
      </div>

      <div className="backtest-horizons">
        {backtest.horizons.map((item) => {
          const hasSamples = item.samples > 0;
          return (
            <article key={item.horizon_days}>
              <div className="backtest-horizon-title">
                <span>未来 {item.horizon_days} 天</span>
                <small>{hasSamples ? `${item.hit_count}/${item.samples} 次命中` : "暂无样本"}</small>
              </div>
              <strong>{hasSamples ? `${item.hit_rate_percent.toFixed(1)}%` : "—"}</strong>
              <span className="backtest-rate-label">命中率</span>
              <div className="backtest-drawdowns">
                <span>平均最大跌幅 <b>{hasSamples ? `-${item.average_max_drawdown_percent.toFixed(2)}%` : "—"}</b></span>
                <span>最深跌幅 <b>{hasSamples ? `-${item.worst_max_drawdown_percent.toFixed(2)}%` : "—"}</b></span>
              </div>
            </article>
          );
        })}
      </div>

      <div className="backtest-signals">
        <div className="backtest-subheading">
          <h3>最近触发记录</h3>
          <span>仅展示最近 5 次</span>
        </div>
        {backtest.recent_signals.length > 0 ? (
          <div className="backtest-table-wrap">
            <table>
              <thead><tr><th>日期</th><th>风险分</th><th>信号价</th><th>1日跌幅</th><th>3日跌幅</th><th>7日跌幅</th></tr></thead>
              <tbody>
                {backtest.recent_signals.map((signal) => (
                  <tr key={signal.timestamp}>
                    <td>{dateFormatter.format(new Date(signal.timestamp))}</td>
                    <td><b>{signal.score}</b></td>
                    <td>{priceFormatter.format(signal.price)}</td>
                    <td>-{(signal.future_drawdowns["1"] ?? 0).toFixed(2)}%</td>
                    <td>-{(signal.future_drawdowns["3"] ?? 0).toFixed(2)}%</td>
                    <td>-{(signal.future_drawdowns["7"] ?? 0).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="backtest-empty">该历史区间内没有风险分上穿 {backtest.risk_threshold} 的独立信号。</p>
        )}
      </div>

      <p className="backtest-methodology">{backtest.methodology} 回测只衡量历史关联，不代表未来表现。</p>
    </section>
  );
}
