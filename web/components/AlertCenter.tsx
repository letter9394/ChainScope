"use client";

import { useState } from "react";

import type { AlertEvent, AlertMetric, AlertOperator, AlertRule, AlertRuleInput } from "@/lib/types";

const coinOptions = [
  { id: "bitcoin", symbol: "BTC" },
  { id: "ethereum", symbol: "ETH" },
  { id: "solana", symbol: "SOL" },
  { id: "gold", symbol: "XAU" },
];

const metricCopy: Record<AlertMetric, { label: string; unit: string }> = {
  risk_score: { label: "综合风险分", unit: "分" },
  price_change_24h: { label: "24 小时涨跌幅", unit: "%" },
};

function ruleSummary(rule: AlertRule) {
  const comparison = rule.operator === "gte" ? "≥" : "≤";
  return `${rule.symbol} · ${metricCopy[rule.metric].label} ${comparison} ${rule.threshold}${metricCopy[rule.metric].unit}`;
}

function timeLabel(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

interface AlertCenterProps {
  rules: AlertRule[];
  events: AlertEvent[];
  busy: boolean;
  onCreate: (input: AlertRuleInput) => Promise<void>;
  onDelete: (ruleId: number) => Promise<void>;
  onAcknowledge: (eventId: number) => Promise<void>;
  onEvaluate: () => Promise<void>;
}

export function AlertCenter({
  rules,
  events,
  busy,
  onCreate,
  onDelete,
  onAcknowledge,
  onEvaluate,
}: AlertCenterProps) {
  const [coinId, setCoinId] = useState("bitcoin");
  const [metric, setMetric] = useState<AlertMetric>("risk_score");
  const [operator, setOperator] = useState<AlertOperator>("gte");
  const [threshold, setThreshold] = useState("65");
  const selectedSymbol = coinOptions.find((coin) => coin.id === coinId)?.symbol ?? coinId;
  const comparisonCopy = operator === "gte" ? "达到或高于" : "达到或低于";
  const thresholdCopy = threshold.trim() || "—";

  const changeMetric = (nextMetric: AlertMetric) => {
    setMetric(nextMetric);
    if (nextMetric === "risk_score") {
      setOperator("gte");
      setThreshold("65");
    } else {
      setOperator("lte");
      setThreshold("-5");
    }
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedThreshold = Number(threshold);
    if (!Number.isFinite(parsedThreshold)) return;
    await onCreate({ coin_id: coinId, metric, operator, threshold: parsedThreshold });
  };

  return (
    <section className="alerts-section" id="alerts">
      <div className="alerts-heading">
        <div>
          <p className="kicker">THRESHOLD MONITORING</p>
          <h2>风险预警中心</h2>
          <p>每 60 秒用最新行情检查一次。只有从安全状态首次越线时才产生新事件，避免重复轰炸。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void onEvaluate()} disabled={busy}>
          {busy ? "检查中…" : "立即检查"}
        </button>
      </div>

      <div className="alerts-grid">
        <div className="panel alert-rule-panel">
          <div className="section-title-row">
            <div><span>01</span><h3>设置监控规则</h3></div>
            <strong>{rules.length} 条启用</strong>
          </div>
          <div className="alert-explainer">
            <strong>阈值 = 你设置的报警线</strong>
            <p>例如风险分报警线设为 65：当风险分从 65 以下升到 65 或更高时，系统记录一次预警。</p>
            <div><span>0–29 低风险</span><span>30–59 中风险</span><span>60–100 高风险</span></div>
          </div>
          <form className="alert-form" onSubmit={submit}>
            <label>资产
              <select value={coinId} onChange={(event) => setCoinId(event.target.value)}>
                {coinOptions.map((coin) => <option key={coin.id} value={coin.id}>{coin.symbol}</option>)}
              </select>
            </label>
            <label>指标
              <select value={metric} onChange={(event) => changeMetric(event.target.value as AlertMetric)}>
                <option value="risk_score">综合风险分</option>
                <option value="price_change_24h">24 小时涨跌幅</option>
              </select>
            </label>
            <label>条件
              <select value={operator} onChange={(event) => setOperator(event.target.value as AlertOperator)}>
                <option value="gte">达到或高于</option>
                <option value="lte">达到或低于</option>
              </select>
            </label>
            <label>报警线（阈值）
              <div className="threshold-input"><input value={threshold} onChange={(event) => setThreshold(event.target.value)} type="number" min="-100" max="100" step="0.1" required /><span>{metricCopy[metric].unit}</span></div>
            </label>
            <div className="alert-rule-preview">
              <strong>当前规则</strong>
              <span>当 {selectedSymbol} 的{metricCopy[metric].label}{comparisonCopy} {thresholdCopy}{metricCopy[metric].unit}时提醒我。</span>
              <small>{metric === "risk_score" ? "风险分范围为 0–100，分数越高代表市场风险越大。" : "例如设为 -5%，表示 24 小时跌幅达到 5% 或更多时提醒。"}</small>
            </div>
            <button className="primary-button" type="submit" disabled={busy}>保存这条提醒</button>
          </form>

          <div className="rule-list">
            {rules.length === 0 ? <p className="empty-state">还没有规则。可以先创建“BTC 风险分 ≥ 65”。</p> : rules.map((rule) => (
              <article className={`rule-item ${rule.is_triggered ? "triggered" : ""}`} key={rule.id}>
                <div><strong>{ruleSummary(rule)}</strong><span>{rule.is_triggered ? "已越线" : "监控中"}</span></div>
                <button type="button" onClick={() => void onDelete(rule.id)} disabled={busy} aria-label={`删除 ${rule.symbol} 预警规则`}>删除</button>
              </article>
            ))}
          </div>
        </div>

        <div className="panel alert-event-panel">
          <div className="section-title-row">
            <div><span>02</span><h3>预警事件</h3></div>
            <strong>{events.filter((event) => !event.acknowledged_at).length} 条待确认</strong>
          </div>
          <div className="event-list">
            {events.length === 0 ? <p className="empty-state">暂无触发记录。系统会持续检查你创建的规则。</p> : events.map((event) => (
              <article className={`event-item ${event.severity} ${event.acknowledged_at ? "acknowledged" : ""}`} key={event.id}>
                <div className="event-meta"><span>{event.severity === "critical" ? "高风险" : "提醒"}</span><time>{timeLabel(event.triggered_at)}</time></div>
                <h4>{event.title}</h4>
                <p>{event.message}</p>
                {event.acknowledged_at ? <small>已确认</small> : <button type="button" onClick={() => void onAcknowledge(event.id)} disabled={busy}>我知道了</button>}
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
