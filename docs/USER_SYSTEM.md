# 用户系统、数据库与后台预警说明

这次升级把 ChainScope 从“浏览器打开时才检查的单用户演示”改成了具备真实后端状态的多用户系统。

## 数据流

```text
注册 / 登录
  └─ scrypt 密码哈希 → users
  └─ 新账号待验证状态 → email_verifications
  └─ 24 小时签名链接 → 验证邮箱所有权
  └─ HttpOnly 签名 Cookie → 后续身份识别

用户操作
  ├─ user_watchlist           自选资产
  ├─ user_alert_rules         风险规则与越线状态
  ├─ user_alert_events        触发历史与确认状态
  └─ notification_preferences 通知偏好

后台循环（默认 60 秒）
  └─ 找出所有启用规则的用户
  └─ 请求最新行情 / 风险分
  └─ 只在“安全 → 越线”时生成一次事件
  └─ 记录站内通知，并按配置尝试 SMTP 邮件
```

## 安全设计

- 密码使用带随机盐的 `scrypt` 哈希，数据库中不保存明文密码。
- 忘记密码时发送 30 分钟有效的签名链接；修改成功后旧链接立即失效，并自动登录原账号。
- 新注册账号会收到 24 小时有效的签名验证链接；验证前仍可登录和使用站内功能，但不能开启邮件预警或发送测试邮件。
- 登录、注册、找回密码、链接确认和验证邮件重发使用账号与客户端地址双维度滑动窗口限流，超限时返回 `429` 和 `Retry-After`。
- 为兼容已经上线的账号，升级前创建且没有 `email_verifications` 记录的用户视为已验证。
- 会话保存在 `HttpOnly` Cookie 中，前端 JavaScript 无法读取；生产环境仅通过 HTTPS 发送。
- 自选、规则、事件和通知设置的每条查询都包含 `user_id` 条件。
- Render 通过 `generateValue: true` 创建生产专用 `SESSION_SECRET`，不把密钥提交到 GitHub。
- 当前限流状态保存在 Web 进程内；正式多实例部署应迁移到 Redis 等共享存储，并继续完成 CSRF 防护审计与数据库迁移工具。

## 免费部署的边界

后台调度器和 Web 服务运行在同一进程中，不额外产生 Render Cron Job 费用。免费 Web Service 休眠时调度也会暂停；收到访问并唤醒后自动恢复。Render 免费 PostgreSQL 当前还有 30 天期限，因此正式长期服务应升级数据库或迁移到其他长期 PostgreSQL。

## 开启邮箱通知

不配置任何密钥时，站内事件仍可正常工作。Render 免费 Web Service 会封锁 SMTP 端口，因此线上免费部署推荐在 Environment 中添加：

```env
BREVO_API_KEY=
BREVO_SENDER_EMAIL=
```

`BREVO_SENDER_EMAIL` 必须先在 Brevo 中完成验证。API Key 仅保存在 Render，不要提交到 GitHub。免费 Render 通过 HTTPS 443 端口调用 Brevo API。

本地开发或允许 SMTP 出站的付费主机也可以继续使用：

```env
SMTP_HOST=
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_SECURITY=ssl
SMTP_TIMEOUT_SECONDS=15
```

`SMTP_PASSWORD` 必须填写邮箱服务生成的客户端授权码，不要填写邮箱登录密码，也不要提交到 GitHub。

| 发件邮箱 | SMTP_HOST | 端口 | SMTP_SECURITY |
| --- | --- | ---: | --- |
| QQ 邮箱 | `smtp.qq.com` | 465 | `ssl` |
| 网易 163 | `smtp.163.com` | 465 | `ssl` |
| 网易 126 | `smtp.126.com` | 465 | `ssl` |

Brevo 与 SMTP 同时配置时优先使用 Brevo。配置完成并重新部署后，用户可在账号面板中开启邮件通知，并点击“发送测试邮件”。测试邮件永远只发送到当前登录账号的注册邮箱，且同一用户每分钟最多发送一次。
