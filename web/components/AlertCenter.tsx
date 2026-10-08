"use client";

import { useState } from "react";

import type { AlertEvent, AlertMetric, AlertOperator, AlertRule, AlertRuleInput } from "@/lib/types";

const coinOptions = [
  { id: "bitcoin", symbol: "BTC" },
  { id: "ethereum", symbol: "ETH" },
  { id: "solana", symbol: "SOL" },
];

const metricCopy: Record<AlertMetric, { label: string; unit: string }> = {
  risk_score: { label: "综合风险分", unit: "分" },
  price_change_24h: { label: "24 小时涨跌幅", unit: "%" },
};

function ruleSummary(rule: AlertRule) {
  const comparison = rule.operator === "gte" ? "≥" : "≤";
  return `${rule.symbol} · ${metricCopy[rule.metric].label} ${comparison} ${rule.threshold}${metricCopy[rule.metric].unit}`;
}

function isDemoRiskRule(rule: AlertRule) {
  return rule.metric === "risk_score" && rule.operator === "gte" && rule.threshold === 0;
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
  authenticated: boolean;
  loading: boolean;
  rules: AlertRule[];
  events: AlertEvent[];
  busy: boolean;
  feedback: { tone: "success" | "warning" | "error"; message: string } | null;
  onCreate: (input: AlertRuleInput) => Promise<void>;
  onSetEnabled: (ruleId: number, enabled: boolean) => Promise<void>;
  onDelete: (ruleId: number) => Promise<void>;
  onAcknowledge: (eventId: number) => Promise<void>;
  onEvaluate: () => Promise<void>;
}

export function AlertCenter({
  authenticated,
  loading,
  rules,
  events,
  busy,
  feedback,
  onCreate,
  onSetEnabled,
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
  const demoRiskRuleCount = rules.filter((rule) => rule.enabled && isDemoRiskRule(rule)).length;
  const isDemoRiskDraft = metric === "risk_score" && operator === "gte" && threshold.trim() !== "" && Number(threshold) === 0;

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
          <p>登录后，服务在线期间每 60 秒用最新行情检查一次。只有从安全状态首次越线时才产生新事件，避免重复轰炸。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void onEvaluate()} disabled={busy || loading || !authenticated}>
          {busy ? "检查中…" : "立即检查"}
        </button>
      </div>

      {loading ? (
        <div className="panel alert-loading" role="status" aria-live="polite">
          <span className="alert-loading-indicator" aria-hidden="true" />
          正在读取账号和预警记录…
        </div>
      ) : !authenticated ? (
        <div className="auth-gate panel">
          <strong>登录后启用个人风险预警</strong>
          <p>你的规则、触发状态和历史事件会独立保存。请先在页面上方登录或注册。</p>
          <a href="#account">前往登录</a>
        </div>
      ) : <>
        <div className="alert-journey" aria-label="预警使用步骤">
          <span><b>01</b> 设置规则</span>
          <span><b>02</b> 检查是否越线</span>
          <span><b>03</b> 查看并确认事件</span>
        </div>
        {feedback && (
          <p className={`alert-feedback ${feedback.tone}`} role={feedback.tone === "error" ? "alert" : "status"}>
            {feedback.message}
          </p>
        )}
        <div className="alerts-grid" aria-busy={busy}>
        <div className="panel alert-rule-panel">
          <div className="section-title-row">
            <div><span>01</span><h3>设置监控规则</h3></div>
            <strong>{rules.filter((rule) => rule.enabled).length} 条启用</strong>
          </div>
          <div className="alert-explainer">
            <strong>阈值 = 你设置的报警线</strong>
            <p>例如风险分报警线设为 65：当风险分从 65 以下升到 65 或更高时，系统记录一次预警。</p>
            <div><span>0–29 低风险</span><span>30–59 中风险</span><span>60–100 高风险</span></div>
          </div>
          {demoRiskRuleCount > 0 && (
            <div className="alert-demo-warning" role="note">
              <strong>检测到 {demoRiskRuleCount} 条已启用的 0 分验收规则</strong>
              <p>风险分 ≥ 0 只适合验证预警流程，不适合作为日常报警线。保留验收证据后请复核这些规则；删除规则会同时删除关联的预警历史。</p>
            </div>
          )}
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
              {isDemoRiskDraft && <small className="demo-threshold-hint">0 分仅用于验收测试，不建议长期启用。</small>}
            </div>
            <button className="primary-button" type="submit" disabled={busy}>保存这条提醒</button>
          </form>

          <div className="rule-list">
            {rules.length === 0 ? <p className="empty-state">还没有规则。可以先创建“BTC 风险分 ≥ 65”。</p> : rules.map((rule) => (
              <article className={`rule-item ${rule.is_triggered && rule.enabled ? "triggered" : ""}`} key={rule.id}>
                <div className="rule-item-copy"><strong>{ruleSummary(rule)}</strong><span>{rule.enabled ? (rule.is_triggered ? "已越线" : "监控中") : "已停用"}{isDemoRiskRule(rule) ? " · 演示阈值" : ""}</span></div>
                <div className="rule-item-actions">
                  <button
                    type="button"
                    onClick={() => void onSetEnabled(rule.id, !rule.enabled)}
                    disabled={busy}
                    aria-label={`${rule.enabled ? "停用" : "启用"} ${ruleSummary(rule)}`}
                  >{rule.enabled ? "停用" : "启用"}</button>
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm("删除这条规则？相关的预警历史也会一并删除，此操作无法撤销。")) {
                        void onDelete(rule.id);
                      }
                    }}
                    disabled={busy}
                    aria-label={`删除 ${rule.symbol} 预警规则`}
                  >删除</button>
                </div>
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
      </>}
    </section>
  );
}
