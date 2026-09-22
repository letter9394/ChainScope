"use client";

import { useEffect, useState } from "react";

import type { AuthUser, NotificationSettings } from "@/lib/types";

type AccountMode = "login" | "register" | "forgot" | "reset";

interface AccountPanelProps {
  user: AuthUser | null | undefined;
  settings: NotificationSettings | null;
  busy: boolean;
  passwordResetToken: string | null;
  onAuthenticate: (mode: "login" | "register", email: string, password: string) => Promise<void>;
  onRequestPasswordReset: (email: string) => Promise<string>;
  onConfirmPasswordReset: (token: string, password: string) => Promise<void>;
  onClearPasswordResetToken: () => void;
  onLogout: () => Promise<void>;
  onSaveSettings: (settings: Pick<NotificationSettings, "email_enabled">) => Promise<void>;
  onSendTestEmail: () => Promise<string>;
}

export function AccountPanel({
  user,
  settings,
  busy,
  passwordResetToken,
  onAuthenticate,
  onRequestPasswordReset,
  onConfirmPasswordReset,
  onClearPasswordResetToken,
  onLogout,
  onSaveSettings,
  onSendTestEmail,
}: AccountPanelProps) {
  const [mode, setMode] = useState<AccountMode>(passwordResetToken ? "reset" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [accountMessage, setAccountMessage] = useState<string | null>(null);

  useEffect(() => {
    if (passwordResetToken) setMode("reset");
  }, [passwordResetToken]);

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

  const submitAccount = async () => {
    setAccountMessage(null);
    if (mode === "forgot") {
      try {
        setAccountMessage(await onRequestPasswordReset(email));
      } catch (reason) {
        setAccountMessage(reason instanceof Error ? reason.message : "重置邮件发送失败");
      }
      return;
    }
    if (mode === "reset") {
      if (!passwordResetToken) {
        setAccountMessage("重置链接无效，请重新申请。");
        return;
      }
      if (password !== passwordConfirmation) {
        setAccountMessage("两次输入的密码不一致。");
        return;
      }
      try {
        await onConfirmPasswordReset(passwordResetToken, password);
      } catch (reason) {
        setAccountMessage(reason instanceof Error ? reason.message : "密码重置失败");
      }
      return;
    }
    await onAuthenticate(mode, email, password);
  };

  const switchMode = (nextMode: AccountMode) => {
    setMode(nextMode);
    setPassword("");
    setPasswordConfirmation("");
    setAccountMessage(null);
    if (nextMode !== "reset" && passwordResetToken) onClearPasswordResetToken();
  };

  if (user === undefined) {
    return <section className="account-panel panel" id="account"><p>正在读取登录状态…</p></section>;
  }

  if (!user) {
    return (
      <section className="account-panel panel" id="account">
        <div className="account-copy">
          <p className="kicker">PERSONAL RISK WORKSPACE</p>
          <h2>{mode === "forgot" ? "通过邮箱找回密码" : mode === "reset" ? "设置新的登录密码" : "登录后保存你的监控配置"}</h2>
          <p>{mode === "forgot"
            ? "输入注册邮箱，我们会发送一封 30 分钟内有效的重置邮件。"
            : mode === "reset"
              ? "设置新密码后会自动登录，原有自选和预警数据都会保留。"
              : "自选、预警规则和事件会按账号隔离，并保存到 PostgreSQL。公开行情和新闻无需登录。"}</p>
        </div>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); void submitAccount(); }}>
          {mode === "login" || mode === "register" ? (
            <div className="auth-tabs">
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => switchMode("login")}>登录</button>
              <button type="button" className={mode === "register" ? "active" : ""} onClick={() => switchMode("register")}>注册</button>
            </div>
          ) : null}
          {mode !== "reset" ? (
            <label>邮箱<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          ) : null}
          {mode !== "forgot" ? (
            <label>{mode === "reset" ? "新密码" : "密码"}<input type="password" minLength={8} maxLength={128} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          ) : null}
          {mode === "reset" ? (
            <label>确认新密码<input type="password" minLength={8} maxLength={128} autoComplete="new-password" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} required /></label>
          ) : null}
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "处理中…" : mode === "login" ? "登录 ChainScope" : mode === "register" ? "创建账号" : mode === "forgot" ? "发送重置邮件" : "保存新密码并登录"}
          </button>
          {mode === "login" ? <button className="secondary-button" type="button" onClick={() => switchMode("forgot")}>忘记密码？</button> : null}
          {mode === "forgot" || mode === "reset" ? <button className="secondary-button" type="button" onClick={() => switchMode("login")}>返回登录</button> : null}
          {mode === "register" ? <small>密码至少 8 位。密码只保存高强度哈希，不保存明文。</small> : null}
          {accountMessage ? <p className="email-test-result" role="status">{accountMessage}</p> : null}
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
