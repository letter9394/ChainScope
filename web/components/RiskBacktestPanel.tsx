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
    return <section className="panel backtest-section skeleton-panel">正在回放多年度历史风险信号…</section>;
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
  const splitDate = dateFormatter.format(new Date(backtest.validation.split_timestamp));
  const featureCoefficientMax = Math.max(
    ...backtest.feature_model.feature_importance.map((item) => Math.abs(item.coefficient)),
    0.001,
  );

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
        <article><span>历史覆盖</span><strong>{backtest.history_days} 日</strong></article>
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

      <section className="backtest-quality">
        <div className="backtest-subheading">
          <h3>模型有效性</h3>
          <span>{backtest.quality.horizon_days} 日跌幅事件 · 与市场自然发生率比较</span>
        </div>
        <div className="backtest-quality-grid">
          <article>
            <span>市场基准</span>
            <strong>{backtest.quality.baseline_hit_rate_percent.toFixed(1)}%</strong>
            <small>{backtest.quality.event_days}/{backtest.quality.evaluated_days} 个评估日自然出现目标跌幅</small>
          </article>
          <article>
            <span>信号精确率</span>
            <strong>{backtest.quality.precision_percent.toFixed(1)}%</strong>
            <small>{backtest.quality.true_positive_count} 次命中 · {backtest.quality.false_positive_count} 次误报</small>
          </article>
          <article className={backtest.quality.lift > 1 ? "positive" : "negative"}>
            <span>相对提升 Lift</span>
            <strong>{backtest.quality.lift.toFixed(2)}×</strong>
            <small>{backtest.quality.lift > 1 ? "优于随机日期基准" : "未超过随机日期基准"}</small>
          </article>
          <article>
            <span>召回率 / 漏报率</span>
            <strong>{backtest.quality.recall_percent.toFixed(1)}% / {backtest.quality.miss_rate_percent.toFixed(1)}%</strong>
            <small>整体准确率 {backtest.quality.accuracy_percent.toFixed(1)}% · 类别不均衡时仅作辅助</small>
          </article>
        </div>
      </section>

      <div className="backtest-analysis-grid">
        <section className="backtest-analysis-card">
          <div className="backtest-subheading">
            <h3>时间外验证</h3>
            <span>以 {splitDate} 为分界 · {backtest.validation.horizon_days} 日结果</span>
          </div>
          <div className="backtest-validation-grid">
            <article>
              <span>前 70% 历史区间</span>
              <strong>{backtest.validation.training_hit_rate_percent.toFixed(1)}%</strong>
              <small>{backtest.validation.training_signal_count} 次信号 · {backtest.validation.training_points} 个评估日</small>
            </article>
            <article className="holdout">
              <span>后 30% 留出区间</span>
              <strong>{backtest.validation.holdout_hit_rate_percent.toFixed(1)}%</strong>
              <small>{backtest.validation.holdout_signal_count} 次信号 · {backtest.validation.holdout_points} 个评估日</small>
            </article>
          </div>
        </section>

        <section className="backtest-analysis-card">
          <div className="backtest-subheading">
            <h3>市场阶段分层</h3>
            <span>{backtest.validation.horizon_days} 日命中率</span>
          </div>
          <div className="backtest-regime-grid">
            {backtest.regimes.map((item) => (
              <article key={item.regime} data-regime={item.regime}>
                <span>{item.label}</span>
                <strong>{item.signal_count ? `${item.hit_rate_percent.toFixed(1)}%` : "—"}</strong>
                <small>{item.signal_count} 次信号 · 平均跌幅 {item.signal_count ? `${item.average_max_drawdown_percent.toFixed(2)}%` : "—"}</small>
              </article>
            ))}
          </div>
        </section>
      </div>

      <section className="backtest-sensitivity">
        <div className="backtest-subheading">
          <h3>阈值敏感性</h3>
          <span>检验结论是否过度依赖单一阈值</span>
        </div>
        <div className="backtest-sensitivity-grid">
          {backtest.sensitivity.map((item) => (
            <article key={item.threshold} className={item.threshold === backtest.risk_threshold ? "active" : ""}>
              <span>风险分 ≥ {item.threshold}</span>
              <strong>{item.signal_count ? `${item.hit_rate_percent.toFixed(1)}%` : "—"}</strong>
              <small>{item.signal_count} 次信号 · {item.horizon_days} 日平均跌幅 {item.signal_count ? `${item.average_max_drawdown_percent.toFixed(2)}%` : "—"}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="backtest-walk-forward">
        <div className="backtest-subheading">
          <h3>Walk-forward 滚动验证</h3>
          <span>3 轮扩展训练 · 每轮保留 {backtest.walk_forward.embargo_days} 日标签隔离</span>
        </div>
        <div className="backtest-walk-summary">
          <article><span>留出期基准</span><strong>{backtest.walk_forward.baseline_hit_rate_percent.toFixed(1)}%</strong></article>
          <article><span>留出期精确率</span><strong>{backtest.walk_forward.precision_percent.toFixed(1)}%</strong></article>
          <article className={backtest.walk_forward.lift > 1 ? "positive" : "negative"}><span>留出期 Lift</span><strong>{backtest.walk_forward.lift.toFixed(2)}×</strong></article>
          <article><span>留出期召回率</span><strong>{backtest.walk_forward.recall_percent.toFixed(1)}%</strong></article>
        </div>
        <div className="backtest-table-wrap backtest-walk-table">
          <table>
            <thead><tr><th>轮次</th><th>留出区间</th><th>训练点</th><th>所选阈值</th><th>信号/事件</th><th>基准</th><th>精确率</th><th>Lift</th></tr></thead>
            <tbody>
              {backtest.walk_forward.folds.map((fold) => (
                <tr key={fold.fold}>
                  <td>第 {fold.fold} 轮</td>
                  <td>{dateFormatter.format(new Date(fold.holdout_start))}—{dateFormatter.format(new Date(fold.holdout_end))}</td>
                  <td>{fold.training_points}</td>
                  <td>≥ {fold.selected_threshold}</td>
                  <td>{fold.holdout_signal_count}/{fold.holdout_event_count}</td>
                  <td>{fold.baseline_hit_rate_percent.toFixed(1)}%</td>
                  <td>{fold.precision_percent.toFixed(1)}%</td>
                  <td>{fold.lift.toFixed(2)}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="backtest-feature-model">
        <div className="backtest-subheading">
          <h3>v0.4 特征模型实验</h3>
          <span>{backtest.feature_model.model_name} · {backtest.feature_model.target}</span>
        </div>
        {backtest.feature_model.status === "validated" ? (
          <>
            <div className={`feature-verdict ${backtest.feature_model.promoted ? "promoted" : "rejected"}`}>
              <strong>{backtest.feature_model.promoted ? "达到晋级门槛" : "暂不晋级"}</strong>
              <span>{backtest.feature_model.verdict}</span>
            </div>
            <div className="feature-model-comparison">
              <article>
                <span>v0.3 固定规则 · 留出期</span>
                <strong>{backtest.walk_forward.lift.toFixed(2)}× Lift</strong>
                <small>精确率 {backtest.walk_forward.precision_percent.toFixed(1)}% · {backtest.walk_forward.signal_count} 次信号</small>
              </article>
              <article className={backtest.feature_model.promoted ? "winner" : "candidate"}>
                <span>v0.4 特征模型 · 留出期</span>
                <strong>{backtest.feature_model.lift.toFixed(2)}× Lift</strong>
                <small>精确率 {backtest.feature_model.precision_percent.toFixed(1)}% · {backtest.feature_model.signal_count} 次信号</small>
              </article>
            </div>
            <div className="feature-model-details">
              <div>
                <div className="backtest-subheading">
                  <h3>可解释特征系数</h3>
                  <span>标准化后绝对值排序</span>
                </div>
                <div className="feature-importance-list">
                  {backtest.feature_model.feature_importance.slice(0, 6).map((item) => (
                    <article key={item.key}>
                      <div><span>{item.label}</span><b>{item.coefficient > 0 ? "+" : ""}{item.coefficient.toFixed(3)}</b></div>
                      <i className={item.direction} style={{ width: `${Math.max(6, Math.abs(item.coefficient) / featureCoefficientMax * 100)}%` }} />
                    </article>
                  ))}
                </div>
              </div>
              <div>
                <div className="backtest-subheading">
                  <h3>实验模型指标</h3>
                  <span>{backtest.feature_model.total_holdout_points} 个留出评估日</span>
                </div>
                <div className="feature-metric-grid">
                  <article><span>市场基准</span><strong>{backtest.feature_model.baseline_hit_rate_percent.toFixed(1)}%</strong></article>
                  <article><span>召回率</span><strong>{backtest.feature_model.recall_percent.toFixed(1)}%</strong></article>
                  <article><span>准确率</span><strong>{backtest.feature_model.accuracy_percent.toFixed(1)}%</strong></article>
                  <article><span>漏报率</span><strong>{backtest.feature_model.miss_rate_percent.toFixed(1)}%</strong></article>
                </div>
              </div>
            </div>
            <div className="backtest-table-wrap feature-fold-table">
              <table>
                <thead><tr><th>轮次</th><th>留出区间</th><th>概率阈值</th><th>信号/事件</th><th>基准</th><th>精确率</th><th>Lift</th></tr></thead>
                <tbody>
                  {backtest.feature_model.folds.map((fold) => (
                    <tr key={fold.fold}>
                      <td>第 {fold.fold} 轮</td>
                      <td>{dateFormatter.format(new Date(fold.holdout_start))}—{dateFormatter.format(new Date(fold.holdout_end))}</td>
                      <td>≥ {fold.probability_threshold_percent.toFixed(0)}%</td>
                      <td>{fold.holdout_signal_count}/{fold.holdout_event_count}</td>
                      <td>{fold.baseline_hit_rate_percent.toFixed(1)}%</td>
                      <td>{fold.precision_percent.toFixed(1)}%</td>
                      <td>{fold.lift.toFixed(2)}×</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="backtest-empty">{backtest.feature_model.verdict}</p>
        )}
      </section>

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
