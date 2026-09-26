# ChainScope — Web3 Intelligent Market Analysis and Risk Alert Platform

ChainScope is a full-stack Web3 market intelligence and risk alert platform built as a portfolio and learning project. It combines crypto and spot-gold quotes, professional candlestick charts, bilingual news, and explainable risk indicators in one interface. Version 1.1 adds email accounts, per-user isolation, PostgreSQL persistence, server-side alert checks, in-app notifications, and HTTPS/SMTP email delivery.

## Highlights

- Near-real-time BTC, ETH, and SOL quotes via Binance WebSocket, plus 15-second XAU and REST snapshot refreshes
- Automatic 15-second polling fallback when the live stream is unavailable
- Click-to-switch candlestick charts with 1/5/15/30-minute, 1/4-hour, daily, and weekly intervals
- FastAPI proxies Binance Spot candles for BTC, ETH, and SOL; gold defaults to a professional TradingView `OANDA:XAUUSD` chart and offers an explicit in-app fallback
- Moving averages, volume, and a separate MACD pane are enabled by default, with configurable MA/BOLL/RSI/MACD parameters, crosshair OHLC inspection, fullscreen, pan, and zoom controls
- In-app candles update incrementally every two seconds; the gold fallback can switch between a live PAXG proxy and delayed Massive XAU/USD history
- Transparent 0–100 score based on volatility, maximum drawdown, volume anomaly, and momentum
- A 365-day rolling historical backtest reports high-risk signal hit rates and forward maximum drawdowns over 1, 3, and 7 days
- Live CoinDesk news with source links, sentiment labels, and on-demand English-to-Chinese translation
- Optional OpenAI-compatible news analysis with an honest rule-based fallback
- Signed HttpOnly sessions, scrypt password hashes, one-time password recovery, and 24-hour email ownership verification before email alerts can be enabled
- Sliding-window protection for registration, login, password reset, and verification resend, keyed by both account and client address with standard `429` / `Retry-After` responses
- Per-user watchlists, rules, events, and notification preferences backed by PostgreSQL (SQLite fallback for local development)
- Threshold rules for risk score and 24-hour price change, checked every 60 seconds while the server is awake
- Transition-based alert events with acknowledgement and history, without repeated notification spam
- Brevo HTTPS API for free Render deployments, plus QQ Mail, NetEase Mail, and custom SMTP fallback with a self-test endpoint
- Cache, retry, timeout, validation, tests, Docker, and CI configuration

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

## Public deployment

The root `render.yaml` and multi-stage `Dockerfile` deploy the exported Next.js frontend and FastAPI backend as one same-origin Render service. On Render's free tier, the service sleeps when idle and its SQLite data is ephemeral. Use PostgreSQL or a paid persistent disk for production persistence.

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
