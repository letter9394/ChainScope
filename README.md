# ChainScope Web3智能市场分析与风险预警平台

[English](README_EN.md) · [学习笔记](docs/LEARNING_NOTES.md) · [用户系统说明](docs/USER_SYSTEM.md) · [贡献指南](CONTRIBUTING.md)

ChainScope 是一个面向学习与作品集展示的 Web3 智能市场分析与风险预警平台。它把加密资产与黄金现货行情、专业 K 线、中英双语新闻和可解释风险指标放在同一张仪表盘中。v1.1 已加入邮箱账号、用户数据隔离、PostgreSQL 持久化、后台定时检查、站内通知和 SMTP 邮件预警。

> 当前版本是可独立运行的 MVP，不连接交易账户，不执行买卖，也不构成投资建议。

## 项目亮点

- BTC、ETH、SOL 使用 Binance WebSocket 约每秒推送，XAU 与后端快照每 15 秒校准
- WebSocket 不可用时自动退回 15 秒轮询，不让行情区域失去数据
- 点击任一资产即可切换 TradingView K 线，支持 1/5/15/30 分钟、1/4 小时、日线和周线
- 根据波动率、最大回撤、成交量异常和短期动量计算 0–100 风险分
- 接入 Binance Futures 资金费率、未平仓合约、多空比，并每 10 秒更新
- 通过 WebSocket 实时累计页面打开后的强平事件，区分多单与空单强平
- 将恐慌贪婪指数和负面新闻占比纳入复合风险评分
- 每项风险指标都有权重、数值和中文解释，便于追溯评分依据
- 聚合 CoinDesk 新闻并提供来源链接、情绪标签和按需中英翻译
- 支持 OpenAI 兼容接口；未配置密钥时自动使用规则分析并明确标注
- 邮箱注册/登录使用 HttpOnly 签名 Cookie，密码只保存 scrypt 哈希；支持一次性邮件找回密码
- PostgreSQL 按用户隔离自选、预警规则、事件与通知设置；本地开发可退回 SQLite
- 自定义“风险分”或“24 小时涨跌幅”阈值，服务器在线时每 60 秒后台检查
- 仅在安全状态首次越线时生成事件，避免重复通知；支持确认和历史追溯
- 站内通知默认可用；支持 QQ、网易和自定义 SMTP 邮件预警及一键测试
- 对上游接口提供缓存、超时、重试和友好错误处理
- 提供自动化测试、Docker 配置和 GitHub Actions 持续集成

## 系统架构

```text
浏览器 / Next.js 仪表盘（3100）
 |       |                |
 |   Binance WebSocket    | 约1秒加密行情
 |   TradingView          | K线
 v
FastAPI 服务（8000） ── 后台预警调度器（60 秒）
 /        |          |       |       \
CoinGecko Binance Futures Gold API CoinDesk PostgreSQL
行情历史   衍生品/情绪    黄金现价  RSS新闻  用户/自选/预警/通知
```

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js 15、React 19、TypeScript、TradingView Advanced Chart |
| 后端 | Python 3、FastAPI、Pydantic、HTTPX |
| 数据 | Binance Spot/Futures REST 与 WebSocket、CoinGecko、Gold API、Alternative.me、CoinDesk RSS、PostgreSQL / SQLite |
| 测试 | Pytest、FastAPI TestClient、TypeScript typecheck |
| 工程化 | Docker Compose、GitHub Actions、PowerShell 启停脚本 |

## 风险评分如何计算

复合风险分最高为 100 分；实时衍生品数据可用时使用 v0.2 模型，否则自动退回原有基础模型：

| 指标 | 权重上限 | 含义 |
| --- | ---: | --- |
| 技术面合计 | 约 70 | 年化波动率、最大回撤、成交量异常与短期动量 |
| 资金费率 | 8 | 绝对值过高代表永续合约方向拥挤 |
| 5分钟持仓变化 | 8 | 未平仓合约价值快速变化代表杠杆堆积或撤离 |
| 多空账户拥挤 | 7 | 单边账户占比过高可能放大连锁平仓 |
| 恐慌与贪婪 | 4 | 越接近极端恐慌或极端贪婪，反转风险越高 |
| 负面新闻占比 | 3 | 当前资产近期负面新闻所占比例 |

风险等级划分：0–29 为低风险，30–59 为中风险，60–100 为高风险。实时强平只统计页面打开后的 WebSocket 事件，目前作为观察项展示，不直接计入分数。算法用于演示可解释的数据分析流程，不是投资模型。

## 本地运行

### 方式一：Windows 一键启动

首次运行前需要安装 Python 3.11+、Node.js 20+ 和 pnpm。可通过 `corepack enable` 启用 pnpm，然后分别安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd web
pnpm install
cd ..
```

之后双击 `Start ChainScope.cmd`，或在 PowerShell 中执行：

```powershell
.\scripts\start-local.ps1
```

访问：

- Web 仪表盘：http://localhost:3100
- API 交互文档：http://localhost:8000/docs

停止服务：双击 `Stop ChainScope.cmd`，或运行 `.\scripts\stop-local.ps1`。

### 方式二：Docker Compose

```bash
docker compose up --build
```

## 公网部署

仓库根目录提供 `render.yaml` 和一体化 `Dockerfile`。部署时，前端会导出为静态页面并由 FastAPI 同域提供，因此只有一个公开网址，不需要额外配置跨域地址。将 GitHub 仓库作为 Render Blueprint 导入即可。

Blueprint 会同时创建 Web Service 和 PostgreSQL，并自动注入 `DATABASE_URL` 与随机 `SESSION_SECRET`。首次更新现有 Blueprint 时，需要在 Render 控制台执行一次 **Manual Sync**，让新增数据库资源生效。

Render 免费 Web Service 闲置后会休眠，所以休眠期间后台检查暂停，首次唤醒也可能较慢。免费 PostgreSQL 目前会在创建 30 天后到期，适合作品集演示而非正式生产；长期运行应升级数据库。若需要严格全天候分钟级任务，可升级实例或改用付费 Render Cron Job/独立 Worker。

## 可选环境变量

后端默认不需要 API Key 即可运行。复制 `backend/.env.example` 为 `backend/.env` 可修改配置：

```env
COINGECKO_DEMO_API_KEY=
GOLD_API_URL=https://api.gold-api.com/price/XAU
BINANCE_FUTURES_URL=https://fapi.binance.com
FEAR_GREED_URL=https://api.alternative.me/fng/
DERIVATIVES_CACHE_SECONDS=10
TRANSLATION_API_URL=https://api.mymemory.translated.net/get
GOOGLE_TRANSLATION_API_URL=https://translate.googleapis.com/translate_a/single
TRANSLATION_CACHE_SECONDS=86400
AI_API_KEY=
AI_API_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4.1-mini
DATABASE_URL=postgresql+psycopg://user:password@host:5432/chainscope
SESSION_SECRET=一段足够长的随机字符串
BACKGROUND_ALERTS_ENABLED=true
ALERT_CHECK_SECONDS=60
SMTP_HOST=
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=邮箱授权码，不是登录密码
SMTP_FROM_EMAIL=
SMTP_SECURITY=ssl
```

不要把真实密钥提交到 GitHub。配置 AI 密钥后，新闻模块会调用兼容的 Chat Completions 接口；否则使用本地关键词规则。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd web
pnpm typecheck
pnpm build
```

## 主要 API

| 方法 | 地址 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 服务与数据源状态 |
| GET | `/api/markets` | 市场概览 |
| GET | `/api/coins/{coin_id}/history` | 历史价格和成交量 |
| GET | `/api/coins/{coin_id}/risk` | 可解释风险报告 |
| GET | `/api/coins/{coin_id}/derivatives` | 实时资金费率、持仓量、多空比和市场情绪 |
| GET | `/api/news` | 新闻与情绪分析 |
| POST | `/api/news/translate` | 将一条英文新闻按需翻译为中文 |
| POST | `/api/auth/register`、`/api/auth/login`、`/api/auth/logout` | 用户注册、登录、退出 |
| GET | `/api/auth/me` | 获取当前登录账号 |
| GET / POST / DELETE | `/api/watchlist` | 查询、添加和删除自选资产 |
| GET / POST / DELETE | `/api/alerts/rules` | 查询、创建和删除阈值规则 |
| POST | `/api/alerts/evaluate` | 用最新数据检查全部规则 |
| GET | `/api/alerts/events` | 查询预警事件记录 |
| POST | `/api/alerts/events/{event_id}/acknowledge` | 确认一条预警事件 |
| GET / PUT | `/api/notifications/settings` | 查询或修改邮件通知设置 |
| POST | `/api/notifications/test-email` | 向当前登录邮箱发送测试邮件 |

## 目录结构

```text
ChainScope/
├─ backend/               FastAPI 服务、风险引擎与测试
├─ web/                   Next.js 前端
├─ docs/                  学习笔记与面试解释
├─ scripts/               本地启停脚本
├─ .github/workflows/     持续集成
└─ docker-compose.yml     容器化运行配置
```

## 已知限制与后续计划

- 免费公共数据可能有延迟、限流或短暂不可用
- 新闻情绪分析主要用于作品集演示，不能替代专业研究
- 当前行情覆盖 BTC、ETH、SOL、XAU；XAU 暂不套用加密货币风险评分，也不参与阈值预警
- TradingView 图表依赖其外部服务和用户当前网络；不同报价商的价格可能存在轻微差异
- 新闻翻译由机器生成并按需调用第三方服务，应以英文原文为准
- 免费 Web Service 休眠期间后台预警不会运行；唤醒后自动恢复
- 免费 PostgreSQL 有 30 天期限，正式环境需要付费实例或迁移到长期数据库
- 邮件需要部署者提供 SMTP 邮箱授权码，未配置时仍可使用站内通知
- 免费数据不提供可靠的历史全市场爆仓回补；实时强平仅从页面建立 WebSocket 后累计
- 链上大额转账和交易所净流入需要可靠的链上索引服务/API Key，当前不使用伪造数据代替
- 可进一步加入邮箱所有权预验证、持久化限流、链上数据供应商和策略回测

## License

[MIT](LICENSE)
