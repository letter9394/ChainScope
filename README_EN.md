# ChainScope — Web3 Intelligent Market Analysis and Risk Alert Platform

[中文说明](README.md) · [Portfolio case study (中文)](docs/PORTFOLIO.md) · [Demo script (中文)](docs/DEMO_SCRIPT.md)

ChainScope is a full-stack Web3 market intelligence and risk alert platform built as a portfolio and learning project. It combines crypto and spot-gold quotes, professional candlestick charts, bilingual news, and explainable risk indicators in one interface. Version 1.1 adds email accounts, per-user isolation, PostgreSQL persistence, server-side alert checks, in-app notifications, and HTTPS/SMTP email delivery.

## Highlights

- Near-real-time BTC, ETH, and SOL quotes via Binance WebSocket, plus 15-second XAU and REST snapshot refreshes
- Automatic 15-second polling fallback when the live stream is unavailable
- Click-to-switch candlestick charts with 1/5/15/30-minute, 1/4-hour, daily, and weekly intervals
- FastAPI proxies Binance Spot candles for BTC, ETH, and SOL; gold defaults to a professional TradingView `OANDA:XAUUSD` chart and offers an explicit in-app fallback
- Moving averages, volume, and a separate MACD pane are enabled by default, with configurable MA/BOLL/RSI/MACD parameters, crosshair OHLC inspection, fullscreen, pan, and zoom controls
- In-app candles update incrementally every two seconds; the gold fallback can switch between a live PAXG proxy and delayed Massive XAU/USD history
- Transparent 0–100 score based on volatility, maximum drawdown, volume anomaly, and momentum
- A three-year rolling historical backtest reports 1/3/7-day outcomes, market-regime splits, base-rate lift, precision/recall, and embargoed walk-forward validation
- An interpretable v0.4 logistic-regression experiment compares momentum, volatility, drawdown, volume, moving-average distance, and streak features against v0.3; promotion requires strict single-asset gates and at least two passing assets across BTC, ETH, and SOL
- A v0.5 label-and-calibration study compares fixed 3% drawdowns, volatility-normalized events, and the training set's worst 25%, reporting Brier Score, prevalence-normalized Brier Skill, ECE, and 95% confidence intervals from a 14-day block bootstrap without changing the live model unless at least two assets improve
- Identical backtest evaluations are cached server-side for one hour and all three crypto studies are prewarmed after startup without blocking health checks; `X-ChainScope-Cache` exposes hit/miss diagnostics
- Live CoinDesk news with source links, sentiment labels, and on-demand English-to-Chinese translation
- Optional OpenAI-compatible news analysis with an honest rule-based fallback
- Signed HttpOnly sessions, scrypt password hashes, one-time password recovery, and 24-hour email ownership verification before email alerts can be enabled
- Sliding-window protection for registration, login, password reset, and verification resend, keyed by both account and client address with standard `429` / `Retry-After` responses
- Signed, expiring double-submit CSRF tokens on every unsafe API request, reinforced with `Origin`, `Referer`, and `Sec-Fetch-Site` validation and a single automatic client refresh on token expiry
- Per-user watchlists, rules, events, and notification preferences backed by PostgreSQL (SQLite fallback for local development)
- Threshold rules for risk score and 24-hour price change, checked every 60 seconds while the server is awake
- Transition-based alert events with acknowledgement and history, without repeated notification spam
- Brevo HTTPS API for free Render deployments, plus QQ Mail, NetEase Mail, and custom SMTP fallback with a self-test endpoint
- Cache, retry, timeout, validation, tests, Docker, and CI configuration
- Structured production logs with request IDs, status codes, and latency, plus health reporting for database latency, scheduler cycles, email configuration, uptime, and deployed version

## Quick start on Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd web
pnpm install
cd ..
.\scripts\start-local.ps1
```

Open http://localhost:3100 for the dashboard and http://localhost:8000/docs for the API documentation.

Application startup automatically applies versioned Alembic migrations. For a manual, legacy-safe migration, run `cd backend` followed by `..\.venv\Scripts\python.exe -m app.migrations`; the command validates and adopts an existing pre-Alembic schema before upgrading it.

## Public deployment

The root `render.yaml` and multi-stage `Dockerfile` deploy the exported Next.js frontend and FastAPI backend as one same-origin Render service. On Render's free tier, the service sleeps when idle and its SQLite data is ephemeral. Use PostgreSQL or a paid persistent disk for production persistence.

The browser obtains a signed token from `GET /api/auth/csrf`. Every `POST`, `PUT`, `PATCH`, and `DELETE` request must return that token in the `X-CSRF-Token` header while the matching host-only cookie is present. Requests from untrusted origins are rejected with `403` before route logic runs.

The crypto cards use Binance's one-second ticker stream while CoinGecko provides the normalized fallback snapshot. The XAU reference quote comes from Gold API and uses USD per troy ounce. BTC, ETH, and SOL render server-proxied Binance Spot data with TradingView Lightweight Charts. Gold defaults to the TradingView Advanced Chart for `OANDA:XAUUSD`, with a user-selectable in-app fallback. That fallback uses a clearly labeled live PAXG/USDT trend proxy or, when `MASSIVE_API_KEY` is configured, Massive `C:XAUUSD` history. Massive's free Currencies Basic plan only exposes finalized historical minute bars, so `MASSIVE_DATA_DELAY_DAYS` defaults to `2`; paid real-time plans can set it to `0`. XAU is intentionally excluded from the crypto-specific risk score and threshold alerts, and machine-translated news should always be checked against the linked English original.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd web
pnpm typecheck
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

See the [Chinese README](README.md) for architecture, API routes, environment variables, scoring methodology, and limitations.

## Disclaimer

This project is for educational purposes. It does not provide investment advice or execute trades.

## License

[MIT](LICENSE)
