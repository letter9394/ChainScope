"use client";

import { useEffect, useState } from "react";

import type { AuthUser, NotificationSettings } from "@/lib/types";

interface AccountPanelProps {
  user: AuthUser | null | undefined;
  settings: NotificationSettings | null;
  busy: boolean;
  onAuthenticate: (mode: "login" | "register", email: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
  onSaveSettings: (settings: Pick<NotificationSettings, "email_enabled" | "telegram_enabled" | "telegram_chat_id">) => Promise<void>;
}

export function AccountPanel({ user, settings, busy, onAuthenticate, onLogout, onSaveSettings }: AccountPanelProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [chatId, setChatId] = useState("");

  useEffect(() => {
    if (!settings) return;
    setEmailEnabled(settings.email_enabled);
    setTelegramEnabled(settings.telegram_enabled);
    setChatId(settings.telegram_chat_id ?? "");
  }, [settings]);

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
        void onSaveSettings({ email_enabled: emailEnabled, telegram_enabled: telegramEnabled, telegram_chat_id: chatId || null });
      }}>
        <div><strong>通知通道</strong><span>站内通知始终开启</span></div>
        <label className={!settings?.email_available ? "unavailable" : ""}>
          <input type="checkbox" checked={emailEnabled} disabled={!settings?.email_available} onChange={(event) => setEmailEnabled(event.target.checked)} /> 邮件通知
          <small>{settings?.email_available ? "发送到登录邮箱" : "等待管理员配置 SMTP"}</small>
        </label>
        <label className={!settings?.telegram_available ? "unavailable" : ""}>
          <input type="checkbox" checked={telegramEnabled} disabled={!settings?.telegram_available} onChange={(event) => setTelegramEnabled(event.target.checked)} /> Telegram
          <small>{settings?.telegram_available ? "需要你的 Chat ID" : "等待管理员配置 Bot Token"}</small>
        </label>
        {settings?.telegram_available ? <input aria-label="Telegram Chat ID" placeholder="Telegram Chat ID" value={chatId} onChange={(event) => setChatId(event.target.value)} /> : null}
        <button className="primary-button" type="submit" disabled={busy || !settings}>{busy ? "保存中…" : "保存通知设置"}</button>
      </form>
    </section>
  );
}
