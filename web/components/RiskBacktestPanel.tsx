import type { RiskBacktestPortfolioResult, RiskBacktestResult } from "@/lib/types";

interface RiskBacktestPanelProps {
  backtest: RiskBacktestResult | null;
  portfolio: RiskBacktestPortfolioResult | null;
  portfolioError: string | null;
  loading: boolean;
  error: string | null;
  unavailable?: boolean;
  onSelectCoin: (coinId: string) => void;
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
  portfolio,
  portfolioError,
  loading,
  error,
  unavailable = false,
  onSelectCoin,
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
  const temporalStatusCopy = {
    stable: "时间表现稳定",
    mixed: "时间表现混合",
    deteriorating: "检测到性能衰减",
    insufficient_data: "时间样本不足",
  }[backtest.temporal_stability.status];
  const temporalStatusClass = backtest.temporal_stability.status === "stable"
    ? "promoted"
    : backtest.temporal_stability.status === "deteriorating"
      ? "rejected"
      : "watch";

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

      <section className="backtest-portfolio" aria-label="跨资产模型验证">
        <div className="backtest-subheading">
          <h3>跨资产晋级审查</h3>
          <span>至少 2 个资产通过完整留出期门槛</span>
        </div>
        {portfolio ? (
          <>
            <div className={`feature-verdict ${portfolio.promoted ? "promoted" : "rejected"}`}>
              <strong>{portfolio.promoted ? "跨资产达到晋级门槛" : "跨资产暂不晋级"}</strong>
              <span>{portfolio.verdict}</span>
            </div>
            <div className={`feature-verdict ${portfolio.label_study_recommended ? "promoted" : "rejected"}`}>
              <strong>{portfolio.label_study_recommended ? "v0.6 标签可进入影子运行" : "v0.6 标签保持实验状态"}</strong>
              <span>{portfolio.label_study_verdict}</span>
            </div>
            <div className="backtest-portfolio-grid">
              {portfolio.assets.map((asset) => {
                const available = asset.status === "validated";
                return (
                  <button
                    type="button"
                    key={asset.coin_id}
                    className={`${asset.passed ? "passed" : ""} ${asset.coin_id === backtest.coin_id ? "active" : ""}`}
                    onClick={() => onSelectCoin(asset.coin_id)}
                    disabled={!available}
                    aria-label={`查看 ${asset.symbol} 回测`}
                  >
                    <span><b>{asset.symbol}</b>{asset.passed ? "单资产通过" : available ? "未通过" : "不可用"}</span>
                    <strong>{asset.lift === null ? "—" : `${asset.lift.toFixed(2)}× Lift`}</strong>
                    <small>
                      {available
                        ? `精确率 ${(asset.precision_percent ?? 0).toFixed(1)}% · 基准 ${(asset.baseline_hit_rate_percent ?? 0).toFixed(1)}% · ${asset.signal_count} 次信号 · 标签 ${asset.stable_horizons}/2 周期`
                        : "当前历史数据不足或上游暂不可用"}
                    </small>
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <p className="backtest-empty">{portfolioError ?? "正在汇总 BTC、ETH、SOL 的留出期结果…"}</p>
        )}
      </section>

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
              <strong>{backtest.feature_model.promoted ? "单资产候选通过" : "单资产暂不通过"}</strong>
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

      <section className="backtest-label-study">
        <div className="backtest-subheading">
          <h3>v0.5 标签与概率校准实验</h3>
          <span>同一特征、同一滚动留出期，只比较事件定义</span>
        </div>
        {backtest.label_study.status === "validated" ? (
          <>
            <div className={`feature-verdict ${backtest.label_study.recommended ? "promoted" : "rejected"}`}>
              <strong>{backtest.label_study.recommended ? "单资产发现更优标签" : "固定标签仍是基准"}</strong>
              <span>{backtest.label_study.verdict}</span>
            </div>
            <div className="label-study-grid">
              {backtest.label_study.experiments.map((experiment) => (
                <article
                  key={experiment.key}
                  className={backtest.label_study.recommended_key === experiment.key ? "winner" : ""}
                >
                  <div><span>{experiment.label}</span><b>{experiment.lift.toFixed(2)}× Lift</b></div>
                  <p>{experiment.target}</p>
                  <dl>
                    <div><dt>精确率 / 基准</dt><dd>{experiment.precision_percent.toFixed(1)}% / {experiment.baseline_hit_rate_percent.toFixed(1)}%</dd></div>
                    <div><dt>精确率 95% CI</dt><dd>{experiment.precision_confidence_interval ? `${experiment.precision_confidence_interval.lower.toFixed(1)}%–${experiment.precision_confidence_interval.upper.toFixed(1)}%` : "—"}</dd></div>
                    <div><dt>Lift 95% CI</dt><dd>{experiment.lift_confidence_interval ? `${experiment.lift_confidence_interval.lower.toFixed(2)}–${experiment.lift_confidence_interval.upper.toFixed(2)}` : "—"}</dd></div>
                    <div><dt>Brier Score</dt><dd>{experiment.brier_score.toFixed(4)}</dd></div>
                    <div><dt>Brier 95% CI</dt><dd>{experiment.brier_confidence_interval ? `${experiment.brier_confidence_interval.lower.toFixed(4)}–${experiment.brier_confidence_interval.upper.toFixed(4)}` : "—"}</dd></div>
                    <div><dt>Brier Skill</dt><dd>{experiment.brier_skill_score > 0 ? "+" : ""}{experiment.brier_skill_score.toFixed(3)}</dd></div>
                    <div><dt>校准误差 ECE</dt><dd>{experiment.calibration_error_percent.toFixed(1)}%</dd></div>
                    <div><dt>留出期信号</dt><dd>{experiment.signal_count}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
            <p className="label-study-note">95% 区间使用 500 次、14 日循环区块 Bootstrap；不同标签的事件率不同，因此晋级比较使用相对各自自然发生率归一化的 Brier Skill。Lift 区间下界必须高于 1，且至少两轮留出期有效。</p>
          </>
        ) : (
          <p className="backtest-empty">{backtest.label_study.verdict}</p>
        )}
      </section>

      <section className="backtest-label-stability">
        <div className="backtest-subheading">
          <h3>v0.6 跨周期稳定性审查</h3>
          <span>同一替代标签必须同时通过 3 日与 7 日留出期门槛</span>
        </div>
        <div className={`feature-verdict ${backtest.label_stability.stable ? "promoted" : "rejected"}`}>
          <strong>{backtest.label_stability.stable ? "跨周期结果一致" : "跨周期结果不稳定"}</strong>
          <span>{backtest.label_stability.verdict}</span>
        </div>
        <div className="label-study-grid label-stability-grid">
          {backtest.label_stability.horizons.map((review) => (
            <article key={review.horizon_days} className={review.passed ? "winner" : ""}>
              <div><span>未来 {review.horizon_days} 日</span><b>Lift {review.lift.toFixed(2)}×</b></div>
              <p>{review.passed ? "替代标签通过本周期完整门槛" : "本周期继续使用固定3%标签"}</p>
              <dl>
                <div><dt>本周期选择</dt><dd>{review.selected_label}</dd></div>
                <div><dt>Lift 区间下界</dt><dd>{review.lift_confidence_lower === null ? "—" : review.lift_confidence_lower.toFixed(2)}</dd></div>
                <div><dt>Brier Skill</dt><dd>{review.brier_skill_score > 0 ? "+" : ""}{review.brier_skill_score.toFixed(3)}</dd></div>
                <div><dt>周期结论</dt><dd>{review.passed ? "通过" : "未通过"}</dd></div>
              </dl>
            </article>
          ))}
        </div>
        <p className="label-study-note">此门槛检查的是结论能否跨预测窗口复现；只有两个周期推荐同一种替代标签，才继续参加 BTC、ETH、SOL 跨资产审查。</p>
      </section>

      <section className="backtest-temporal-stability">
        <div className="backtest-subheading">
          <h3>v0.7 时间稳定性与漂移监控</h3>
          <span>三轮连续留出期 · 监控当前采用标签，不自动调参</span>
        </div>
        <div className={`feature-verdict ${temporalStatusClass}`}>
          <strong>{temporalStatusCopy}</strong>
          <span>{backtest.temporal_stability.verdict}</span>
        </div>
        <div className="backtest-walk-summary">
          <article><span>监控标签</span><strong>{backtest.temporal_stability.selected_label}</strong></article>
          <article><span>Lift 变化</span><strong>{backtest.temporal_stability.lift_change > 0 ? "+" : ""}{backtest.temporal_stability.lift_change.toFixed(2)}</strong></article>
          <article><span>Brier Skill 变化</span><strong>{backtest.temporal_stability.brier_skill_change > 0 ? "+" : ""}{backtest.temporal_stability.brier_skill_change.toFixed(3)}</strong></article>
          <article><span>事件率变化</span><strong>{backtest.temporal_stability.event_rate_change_percent_points > 0 ? "+" : ""}{backtest.temporal_stability.event_rate_change_percent_points.toFixed(1)}pp</strong></article>
        </div>
        <div className="backtest-table-wrap temporal-stability-table">
          <table>
            <thead><tr><th>时间段</th><th>信号/事件</th><th>市场基准</th><th>精确率</th><th>Lift</th><th>Brier Skill</th><th>结论</th></tr></thead>
            <tbody>
              {backtest.temporal_stability.periods.map((period) => (
                <tr key={period.period}>
                  <td>第 {period.period} 期 · {dateFormatter.format(new Date(period.holdout_start))}—{dateFormatter.format(new Date(period.holdout_end))}</td>
                  <td>{period.signal_count}/{period.event_days}</td>
                  <td>{period.baseline_hit_rate_percent.toFixed(1)}%</td>
                  <td>{period.precision_percent.toFixed(1)}%</td>
                  <td>{period.lift.toFixed(2)}×</td>
                  <td>{period.brier_skill_score > 0 ? "+" : ""}{period.brier_skill_score.toFixed(3)}</td>
                  <td>{period.passed ? "稳定" : "观察"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="label-study-note">“衰减”只是一项模型监控告警：它表示最近留出期相对早期变差，不代表市场方向，也不会触发自动换模。</p>
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
