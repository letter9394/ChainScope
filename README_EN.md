# ChainScope — Web3 Intelligent Market Analysis and Risk Alert Platform

ChainScope is a full-stack Web3 market intelligence and risk alert platform built as a portfolio and learning project. It combines crypto and spot-gold quotes, professional candlestick charts, bilingual news, and explainable risk indicators in one interface. Version 1.1 adds email accounts, per-user isolation, PostgreSQL persistence, server-side alert checks, in-app notifications, and SMTP email delivery.

## Highlights

- Near-real-time BTC, ETH, and SOL quotes via Binance WebSocket, plus 15-second XAU and REST snapshot refreshes
- Automatic 15-second polling fallback when the live stream is unavailable
- Click-to-switch TradingView candlestick charts with 1/5/15/30-minute, 1/4-hour, daily, and weekly intervals
- Transparent 0–100 score based on volatility, maximum drawdown, volume anomaly, and momentum
- Live CoinDesk news with source links, sentiment labels, and on-demand English-to-Chinese translation
- Optional OpenAI-compatible news analysis with an honest rule-based fallback
- Signed HttpOnly sessions, scrypt password hashes, and one-time email password recovery
- Per-user watchlists, rules, events, and notification preferences backed by PostgreSQL (SQLite fallback for local development)
- Threshold rules for risk score and 24-hour price change, checked every 60 seconds while the server is awake
- Transition-based alert events with acknowledgement and history, without repeated notification spam
- QQ Mail, NetEase Mail, and custom SMTP delivery with a self-test endpoint
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

The crypto cards use Binance's one-second ticker stream while CoinGecko provides the normalized fallback snapshot. The XAU quote comes from Gold API and uses USD per troy ounce. Candlestick charts are embedded from TradingView. XAU is intentionally excluded from the crypto-specific risk score and threshold alerts, and machine-translated news should always be checked against the linked English original.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd web
pnpm typecheck
pnpm build
```

See the [Chinese README](README.md) for architecture, API routes, environment variables, scoring methodology, and limitations.

## Disclaimer

This project is for educational purposes. It does not provide investment advice or execute trades.

## License

[MIT](LICENSE)
