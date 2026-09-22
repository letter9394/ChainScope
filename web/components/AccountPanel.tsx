"use client";

import { useEffect, useState } from "react";

import type { AuthUser, NotificationSettings } from "@/lib/types";

interface AccountPanelProps {
  user: AuthUser | null | undefined;
  settings: NotificationSettings | null;
  busy: boolean;
  onAuthenticate: (mode: "login" | "register", email: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
  onSaveSettings: (settings: Pick<NotificationSettings, "email_enabled">) => Promise<void>;
  onSendTestEmail: () => Promise<string>;
}

export function AccountPanel({ user, settings, busy, onAuthenticate, onLogout, onSaveSettings, onSendTestEmail }: AccountPanelProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!settings) return;
    setEmailEnabled(settings.email_enabled);
  }, [settings]);

  const testEmail = async () => {
    setTestMessage(null);
    try {
      setTestMessage(await onSendTestEmail());
    } catch {
      setTestMessage("发送失败，请查看页面错误提示后重试。");
    }
  };

  if (user === undefined) {
    return <section className="account-panel panel" id="account"><p>正在读取登录状态…</p></section>;
  }

  if (!user) {
    return (
      <section className="account-panel panel" id="account">
        <div className="account-copy">
          <p className="kicker">PERSONAL RISK WORKSPACE</p>
          <h2>登录后保存你的监控配置</h2>
          <p>自选、预警规则和事件会按账号隔离，并保存到 PostgreSQL。公开行情和新闻无需登录。</p>
        </div>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); void onAuthenticate(mode, email, password); }}>
          <div className="auth-tabs">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>登录</button>
            <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>注册</button>
          </div>
          <label>邮箱<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>密码<input type="password" minLength={8} maxLength={128} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          <button className="primary-button" type="submit" disabled={busy}>{busy ? "处理中…" : mode === "login" ? "登录 ChainScope" : "创建账号"}</button>
          {mode === "register" ? <small>密码至少 8 位。密码只保存高强度哈希，不保存明文。</small> : null}
        </form>
      </section>
    );
  }

  return (
    <section className="account-panel panel signed-in" id="account">
      <div className="account-copy">
        <p className="kicker">SIGNED IN</p>
        <h2>{user.email}</h2>
        <p>站内预警已启用；服务器在线时会每 {settings?.schedule_seconds ?? 60} 秒在后台检查，不需要一直打开网页。</p>
        <button className="secondary-button" type="button" onClick={() => void onLogout()} disabled={busy}>退出登录</button>
      </div>
      <form className="notification-form" onSubmit={(event) => {
        event.preventDefault();
        void onSaveSettings({ email_enabled: emailEnabled });
      }}>
        <div><strong>通知通道</strong><span>站内通知始终开启</span></div>
        <label className={!settings?.email_available ? "unavailable" : ""}>
          <input type="checkbox" checked={emailEnabled} disabled={!settings?.email_available} onChange={(event) => setEmailEnabled(event.target.checked)} /> 邮件通知
          <small>{settings?.email_available ? `通过${settings.email_provider}发送到当前登录邮箱` : "等待部署者完成 SMTP 配置"}</small>
        </label>
        {settings?.email_sender ? <p className="email-provider-note">发件地址：{settings.email_sender}</p> : null}
        <button className="primary-button" type="submit" disabled={busy || !settings}>{busy ? "保存中…" : "保存通知设置"}</button>
        <button className="secondary-button" type="button" disabled={busy || !settings?.email_available} onClick={() => void testEmail()}>
          {busy ? "发送中…" : "发送测试邮件"}
        </button>
        {testMessage ? <p className="email-test-result" role="status">{testMessage}</p> : null}
      </form>
    </section>
  );
}
