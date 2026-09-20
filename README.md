# ChainScope Web3智能市场分析与风险预警平台

[English](README_EN.md) · [学习笔记](docs/LEARNING_NOTES.md) · [贡献指南](CONTRIBUTING.md)

ChainScope 是一个面向学习与作品集展示的 Web3 智能市场分析与风险预警平台。它把实时行情、历史走势、新闻和可解释风险指标放在同一张仪表盘中，帮助用户理解资产为什么被判断为低、中或高风险，而不是只给出一个缺少依据的分数。当前 MVP 通过持续刷新和风险等级变化实现页面内预警，消息推送和链上指标属于后续迭代。

> 当前版本是可独立运行的 MVP，不连接交易账户，不执行买卖，也不构成投资建议。

## 项目亮点

- 实时展示 BTC、ETH、SOL 的价格、24 小时涨跌和交易量
- 绘制 30 天价格趋势图，支持币种切换
- 根据波动率、最大回撤、成交量异常和短期动量计算 0–100 风险分
- 每项风险指标都有权重、数值和中文解释，便于追溯评分依据
- 聚合 CoinDesk 新闻并提供来源链接与情绪标签
- 支持 OpenAI 兼容接口；未配置密钥时自动使用规则分析并明确标注
- 使用 SQLite 保存本地自选列表，刷新页面后仍然存在
- 对上游接口提供缓存、超时、重试和友好错误处理
- 提供自动化测试、Docker 配置和 GitHub Actions 持续集成

## 系统架构

```text
浏览器 / Next.js 仪表盘（3100）
              |
              v
     FastAPI 服务（8000）
       /       |        \
 CoinGecko   CoinDesk   SQLite
 行情/历史    RSS 新闻   自选列表
       |
  缓存 + 重试 + 风险评分
```

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js 15、React 19、TypeScript、原生 SVG 图表 |
| 后端 | Python 3、FastAPI、Pydantic、HTTPX |
| 数据 | CoinGecko Public API、CoinDesk RSS、SQLite |
| 测试 | Pytest、FastAPI TestClient、TypeScript typecheck |
| 工程化 | Docker Compose、GitHub Actions、PowerShell 启停脚本 |

## 风险评分如何计算

综合风险分最高为 100 分：

| 指标 | 权重上限 | 含义 |
| --- | ---: | --- |
| 年化波动率 | 40 | 价格日收益率的离散程度，越大代表不确定性越高 |
| 最大回撤 | 35 | 观察窗口内从高点到低点的最大跌幅 |
| 成交量异常 | 15 | 最新成交量相对近期平均值的偏离程度 |
| 短期动量 | 10 | 最近一段时间快速上涨或下跌造成的追涨杀跌风险 |

风险等级划分：0–34 为低风险，35–64 为中风险，65–100 为高风险。算法用于演示可解释的数据分析流程，不是投资模型。

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

## 可选环境变量

后端默认不需要 API Key 即可运行。复制 `backend/.env.example` 为 `backend/.env` 可修改配置：

```env
COINGECKO_DEMO_API_KEY=
AI_API_KEY=
AI_API_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4.1-mini
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
| GET | `/api/news` | 新闻与情绪分析 |
| GET / POST / DELETE | `/api/watchlist` | 查询、添加和删除自选资产 |

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
- 当前仅覆盖 BTC、ETH、SOL，后续可增加搜索、告警和用户系统
- 可进一步加入回测、WebSocket 实时流、PostgreSQL 与云端部署

## License

[MIT](LICENSE)
