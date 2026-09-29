# ChainScope Web3智能市场分析与风险预警平台

[English](README_EN.md) · [作品集说明](docs/PORTFOLIO.md) · [演示脚本](docs/DEMO_SCRIPT.md) · [学习笔记](docs/LEARNING_NOTES.md) · [用户系统说明](docs/USER_SYSTEM.md) · [贡献指南](CONTRIBUTING.md)

ChainScope 是一个面向学习与作品集展示的 Web3 智能市场分析与风险预警平台。它把加密资产与黄金现货行情、专业 K 线、中英双语新闻和可解释风险指标放在同一张仪表盘中。v1.1 已加入邮箱账号、用户数据隔离、PostgreSQL 持久化、后台定时检查、站内通知和 SMTP 邮件预警。

> 当前版本是可独立运行的 MVP，不连接交易账户，不执行买卖，也不构成投资建议。

## 项目亮点

- BTC、ETH、SOL 使用 Binance WebSocket 约每秒推送，XAU 与后端快照每 15 秒校准
- WebSocket 不可用时自动退回 15 秒轮询，不让行情区域失去数据
- 点击任一资产即可切换 K 线，支持 1/5/15/30 分钟、1/4 小时、日线和周线
- BTC、ETH、SOL 使用 FastAPI 转发的 Binance Spot 站内图；黄金默认使用 TradingView `OANDA:XAUUSD` 专业实时图，并可切换到站内备用图
- 默认展示均线、成交量和独立 MACD 副图，可切换 BOLL、RSI，自定义各项指标参数，并支持十字光标历史 OHLC、全屏、拖动和缩放
- 站内 K 线每 2 秒增量更新；黄金备用图可在 PAXG 实时代理与免费 Massive 延迟 XAU/USD 历史线之间切换
- 根据波动率、最大回撤、成交量异常和短期动量计算 0–100 风险分
- 默认使用 3 年历史数据回放 30 日滚动风险模型，展示未来 1/3/7 日表现、牛熊/震荡分层、市场基准与 Lift、精确率/召回率，以及带标签隔离的三轮 Walk-forward 验证
- 内置 v0.4 可解释逻辑回归实验，使用动量、波动率、回撤、成交量、均线偏离和连续涨跌等历史特征；单资产完整达标且至少两个资产通过跨资产审查后才允许进入影子运行
- 增加 v0.5 标签与概率校准实验，对照固定 3% 跌幅、波动率归一化和训练集最差 25% 三种事件定义，并报告 Brier Score 与 ECE；替代标签仍需至少两个资产独立改善才允许进入影子运行
- 增加 v0.6 跨周期稳定性审查；同一替代标签必须在 3 日与 7 日留出期都通过完整门槛，才进入 BTC、ETH、SOL 跨资产复核
- 增加 v0.7 时间稳定性与模型漂移监控；逐轮展示事件率、精确率、Lift 与 Brier Skill 的变化，并将稳定、混合、衰减和样本不足明确分级
- 增加 v0.8 模型漂移告警闭环；后台定期保存 BTC、ETH、SOL 每日快照，只在状态真正迁移时生成一次可追溯事件，并把运行状态纳入健康检查
- 接入 Binance Futures 资金费率、未平仓合约、多空比，并每 10 秒更新
- 通过 WebSocket 实时累计页面打开后的强平事件，区分多单与空单强平
- 将恐慌贪婪指数和负面新闻占比纳入复合风险评分
- 每项风险指标都有权重、数值和中文解释，便于追溯评分依据
- 聚合 CoinDesk 新闻并提供来源链接、情绪标签和按需中英翻译
- 支持 OpenAI 兼容接口；未配置密钥时自动使用规则分析并明确标注
- 邮箱注册/登录使用 HttpOnly 签名 Cookie，密码只保存 scrypt 哈希；新账号需完成 24 小时有效的邮箱验证后才能开启邮件预警
- 登录、注册、找回密码和验证邮件重发均有 IP＋账号双维度滑动窗口限流，并返回标准 `429` / `Retry-After`
- 所有写请求使用带时效签名的双提交 CSRF Token，并同时校验 `Origin` / `Referer` / `Sec-Fetch-Site`；令牌失效时前端仅自动刷新重试一次
- PostgreSQL 按用户隔离自选、预警规则、事件与通知设置；本地开发可退回 SQLite
- 自定义“风险分”或“24 小时涨跌幅”阈值，服务器在线时每 60 秒后台检查
- 仅在安全状态首次越线时生成事件，避免重复通知；支持确认和历史追溯
- 站内通知默认可用；支持 QQ、网易和自定义 SMTP 邮件预警及一键测试
- 对上游接口提供缓存、超时、重试和友好错误处理
- 生产环境输出带请求编号、状态码和耗时的 JSON 日志；健康检查报告数据库延迟、调度器最近运行状态、邮件配置、运行时间与部署版本
- 提供自动化测试、Docker 配置和 GitHub Actions 持续集成

## 系统架构

```text
浏览器 / Next.js 仪表盘（3100）
 ├─ Binance WebSocket：约 1 秒加密行情
 ├─ TradingView OANDA:XAUUSD：黄金默认专业实时图
 ├─ Lightweight Charts：站内加密 K 线与黄金备用图
 └─ REST API
     v
FastAPI 服务（8000） ── Binance Spot K线代理 ── 后台预警调度器（60 秒）
 /        |          |       |       \
CoinGecko Binance Futures Gold API CoinDesk PostgreSQL
行情历史   衍生品/情绪    黄金现价  RSS新闻  用户/自选/预警/通知
```

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js 15、React 19、TypeScript、TradingView Advanced Chart / Lightweight Charts |
| 后端 | Python 3、FastAPI、Pydantic、HTTPX |
| 数据 | Binance Spot/Futures REST 与 WebSocket、CoinGecko、Gold API、Alternative.me、CoinDesk RSS、PostgreSQL / SQLite |
| 测试 | Pytest、FastAPI TestClient、Playwright、TypeScript typecheck |
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

### 历史回测口径

回测默认使用 3 年日线数据和 30 日滚动基础价格模型。只有风险分从 60 以下首次上穿至 60 或以上时才记录一条独立信号，避免连续高风险日期被重复计数。信号日之后分别观察 1、3、7 天，以期间相对信号日收盘价的最大跌幅达到 3% 作为“命中”。市场阶段只依据每个信号日前 90 天的价格判定。模型精确率会与任意评估日发生同类跌幅的自然概率比较，得到 Lift，并同时报告准确率、召回率和漏报率。三轮 Walk-forward 每轮只用此前数据从候选阈值中选择参数，并剔除训练末尾与预测周期等长的标签隔离带，防止未来标签跨入训练集。衍生品、情绪和新闻缺少可靠的历史快照，因此不纳入回测。结果只说明历史样本关联，不代表未来收益或损失。

v0.4 特征实验使用纯 Python 标准化逻辑回归，所有均值、尺度、权重和概率阈值都只能从每轮训练区间计算。系统会并列展示它与 v0.3 固定规则模型的留出期结果，并设置硬性单资产门槛：整体 Lift 必须超过 1、精确率必须高于市场基准、至少两轮验证有效且信号数量充足。最终还要求 BTC、ETH、SOL 中至少两个资产完整达标，避免只在单一币种上偶然有效。未达标的实验模型会保留分析结果，但不会替换线上风险分。

v0.5 在保持同一特征和同一 Walk-forward 切分的前提下，只改变事件标签：固定 3% 跌幅、仅依赖信号日前波动率的自适应阈值，以及仅由每轮训练集未来跌幅 75 分位数确定的“最差 25%”阈值。每组同时报告 Lift、精确率、Brier Score、按各标签自然发生率归一化的 Brier Skill Score 和期望校准误差（ECE），并通过 500 次、14 日循环区块 Bootstrap 给出精确率、Lift 与 Brier Score 的 95% 置信区间。替代标签必须同时改善区分能力与 Brier Skill，且 Lift 区间下界高于 1，并在至少两轮留出期、至少两个资产上通过，才允许影响线上模型；否则固定标签和当前风险分保持不变。

v0.6 不再只看默认 7 日预测窗口，而是使用完全相同的无前视流程分别验证 3 日与 7 日事件。同一种替代标签只有在两个周期都通过 Lift、Bootstrap 区间、Brier Skill、信号量和有效折数门槛，才被判定为跨周期稳定；之后仍需至少两个资产重复成立。任何周期结论不一致都会自动否决晋级，避免把只适用于单一观察窗口的偶然结果上线。

v0.7 继续复用三轮连续 Walk-forward 留出期，监控当前采用标签在不同时段的市场基准、精确率、Lift、Brier Skill 与校准误差。系统会比较首期和最近一期，将结果标记为稳定、混合、性能衰减或样本不足；漂移告警只用于提示模型复核，不代表市场方向，也不会自动换模或调参。

v0.8 把一次性诊断扩展为可追踪的后台监控：服务启动后及运行期间默认每 6 小时复查三个资产，每个资产每天只保留一条可更新快照；首次结果不误报，只有稳定、混合、衰减或样本不足之间真正发生变化时才写入一次事件。快照和事件通过 PostgreSQL／SQLite 持久化，`/api/risk/drift` 提供历史与最近迁移，`/api/health` 同时报告最近运行时间、成功资产数、迁移事件数和失败资产数。免费 Render 休眠时任务会暂停，因此它是“服务在线期间”的监控，不承诺全天候定时执行。

相同币种、样本长度、滚动窗口和阈值的回测结果会在服务端缓存 1 小时，响应头 `X-ChainScope-Cache` 会标记 `miss` 或 `hit`。服务启动后会在不阻塞健康检查的后台任务中依次预热 BTC、ETH、SOL 三年回测；单个资产预热失败只记录安全日志，不影响其他资产、服务启动或模型结论。

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

应用启动时会自动执行 Alembic 数据库迁移。需要手动检查或执行迁移时：

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.migrations
..\.venv\Scripts\python.exe -m alembic current
```

`app.migrations` 会先安全接管旧版无版本号数据库，再升级到最新版本；不要对尚未接管的旧库直接运行裸 `alembic upgrade head`。

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
CHAIN_SCOPE_ENV=production
LOG_LEVEL=INFO
LOG_JSON=true
COINGECKO_DEMO_API_KEY=
GOLD_API_URL=https://api.gold-api.com/price/XAU
MASSIVE_API_URL=https://api.massive.com
MASSIVE_API_KEY=
MASSIVE_DATA_DELAY_DAYS=2
BINANCE_MARKET_FALLBACK_URLS=https://api.binance.com,https://api-gcp.binance.com,https://api1.binance.com,https://api.binance.us
BINANCE_FUTURES_URL=https://fapi.binance.com
FEAR_GREED_URL=https://api.alternative.me/fng/
RISK_BACKTEST_CACHE_SECONDS=3600
RISK_BACKTEST_PREWARM_ENABLED=true
RISK_DRIFT_MONITOR_ENABLED=true
RISK_DRIFT_CHECK_SECONDS=21600
DERIVATIVES_CACHE_SECONDS=10
CANDLE_CACHE_SECONDS=2
GOLD_CANDLE_CACHE_SECONDS=20
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
BREVO_API_KEY=
BREVO_SENDER_EMAIL=
SMTP_HOST=
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=邮箱授权码，不是登录密码
SMTP_FROM_EMAIL=
SMTP_SECURITY=ssl
```

Render 免费实例会封锁 SMTP 端口，应配置 `BREVO_API_KEY` 与已验证的 `BREVO_SENDER_EMAIL`，通过 HTTPS API 发信。SMTP 配置保留给本地开发或允许 SMTP 出站的付费主机；Brevo 配置完整时会优先使用。黄金主图无需 Key，默认嵌入 TradingView `OANDA:XAUUSD`；`MASSIVE_API_KEY` 只用于站内备用图的精确历史模式。免费 Currencies Basic 只能读取已完成的历史分钟线，因此默认 `MASSIVE_DATA_DELAY_DAYS=2`，并使用 20 秒缓存控制请求额度。付费实时方案可把延迟改为 `0`。不要把任何真实密钥提交到 GitHub。配置 AI 密钥后，新闻模块会调用兼容的 Chat Completions 接口；否则使用本地关键词规则。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd web
pnpm typecheck
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

## 主要 API

| 方法 | 地址 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 数据库、预警调度器、邮件配置、运行时间和部署版本状态 |
| GET | `/api/markets` | 市场概览 |
| GET | `/api/assets/{asset_id}/candles` | 服务器转发的 Binance 加密 K 线与 Massive XAU/USD K 线；支持八种周期 |
| GET | `/api/coins/{coin_id}/history` | 历史价格和成交量 |
| GET | `/api/coins/{coin_id}/risk` | 可解释风险报告 |
| GET | `/api/coins/{coin_id}/risk/backtest` | 多年度回测、基准/Lift、分类指标、市场阶段与 Walk-forward 验证 |
| GET | `/api/risk/backtests` | BTC、ETH、SOL 特征模型留出期汇总与跨资产晋级审查 |
| GET | `/api/risk/drift` | 三资产模型漂移每日快照、状态迁移事件与后台监控状态 |
| GET | `/api/coins/{coin_id}/derivatives` | 实时资金费率、持仓量、多空比和市场情绪 |
| GET | `/api/news` | 新闻与情绪分析 |
| POST | `/api/news/translate` | 将一条英文新闻按需翻译为中文 |
| POST | `/api/auth/register`、`/api/auth/login`、`/api/auth/logout` | 用户注册、登录、退出 |
| GET | `/api/auth/csrf` | 获取写请求所需的签名 CSRF Token，并设置同源 Cookie |
| POST | `/api/auth/email-verification/confirm`、`/api/auth/email-verification/resend` | 确认或重发邮箱验证 |
| POST | `/api/auth/password-reset/request`、`/api/auth/password-reset/confirm` | 申请并完成一次性密码重置 |
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
│  └─ alembic/            版本化数据库迁移
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
- 黄金卡片显示 Gold API 的 XAU/USD 参考价；黄金主图默认使用 TradingView `OANDA:XAUUSD`，其价格口径可能与卡片数据源略有差异
- 站内黄金备用图默认展示明确标注的 Binance PAXG/USDT 走势代理；配置 `MASSIVE_API_KEY` 后还可查看 Massive `C:XAUUSD` 精确历史模式
- Massive 免费 Currencies Basic 不是实时权限，精确历史模式默认延迟两天；需要站内实时 XAU/USD 时应升级数据方案并把 `MASSIVE_DATA_DELAY_DAYS` 改为 `0`
- BTC、ETH、SOL K 线由后端代理 Binance 公共接口并在浏览器内渲染；黄金默认 TradingView 图在部分网络环境中可能需要切换到站内备用图
- 新闻翻译由机器生成并按需调用第三方服务，应以英文原文为准
- 免费 Web Service 休眠期间后台预警不会运行；唤醒后自动恢复
- 免费 PostgreSQL 有 30 天期限，正式环境需要付费实例或迁移到长期数据库
- 邮件需要部署者提供 SMTP 邮箱授权码，未配置时仍可使用站内通知
- 免费数据不提供可靠的历史全市场爆仓回补；实时强平仅从页面建立 WebSocket 后累计
- 链上大额转账和交易所净流入需要可靠的链上索引服务/API Key，当前不使用伪造数据代替
- 当前认证限流保存在单个 Web 进程内；多实例部署应改用 Redis 等共享存储实现全局限流
- 可进一步加入链上数据供应商、多市场走样检验，以及多实例部署所需的 Redis 全局限流

## License

[MIT](LICENSE)
