# ChainScope learning notes

## Why the project is split into frontend and backend

The browser is responsible for interaction and visualization. FastAPI owns external API calls and risk calculations. This separation prevents private API keys and business rules from being exposed in browser code, and it lets each side be tested independently.

## How a market request flows

1. The Next.js page requests `/api/markets` from FastAPI.
2. FastAPI checks its short-lived cache.
3. On a cache miss, CoinGecko supplies the crypto fallback snapshot and Gold API supplies the XAU spot quote.
4. The response is validated with Pydantic models.
5. The browser renders the normalized result.

## How live prices and fallback polling work together

The browser opens one Binance combined WebSocket for BTCUSDT, ETHUSDT, and SOLUSDT ticker events. The stream normally updates the cards about once per second. A separate 15-second REST refresh keeps the XAU quote current and repairs the screen if a stream message is missed. If the WebSocket is blocked or disconnected, the UI explicitly changes to fallback mode and reconnects in the background. Alert evaluation remains on a 60-second schedule so live rendering does not multiply expensive risk calculations.

## Why crypto uses a server proxy while gold has two chart modes

BTC, ETH, and SOL render candles with the open-source TradingView Lightweight Charts library. FastAPI validates the asset and interval, normalizes Binance responses, and applies a cache plus last-known-good fallback. This same-origin path reduces client-side network restrictions and centralizes upstream error handling. Gold is different: the default mode embeds TradingView's professional chart for `OANDA:XAUUSD`, providing a reliable XAU/USD price scale and complete indicator toolbar. A user can switch to the in-app fallback when TradingView is inaccessible. The fallback uses PAXG/USDT as an explicitly labeled live trend proxy or Massive `C:XAUUSD` as delayed exact history when a key is configured. The separation is deliberate: unlike-looking prices from different providers are never presented as the same instrument.

## Why news translation is on demand

Translation is triggered only when a user asks for it, instead of translating every article during each news refresh. This lowers latency and third-party usage, and translated results are cached for 24 hours. The UI keeps a link to the English original because machine translation can lose financial nuance.

## Why the risk score is rule based

A financial risk label should be explainable. The current score combines annualized volatility, maximum drawdown, abnormal volume, and short-term momentum. Each metric contributes a visible number of points. An interviewer can inspect the calculation, reproduce it with test data, and discuss how the thresholds could be calibrated.

## How threshold alerts avoid duplicate events

Each rule stores whether it is currently on the triggered side of the threshold. The system creates an event only when the state changes from safe to triggered. Re-checking the same breached threshold does not create another event. The rule must first return to safety before a later breach can trigger again. Event acknowledgement is separate from this state, so clicking “acknowledge” cannot accidentally create an immediate duplicate.

## Important interview questions

- Why should API keys stay in the backend?
- What problem does a TTL cache solve?
- How does maximum drawdown differ from daily volatility?
- What happens when CoinGecko is unavailable?
- Why is the score educational rather than investment advice?
- Why should an alert trigger on a state transition instead of on every polling cycle?
- Why combine WebSocket push data with a slower REST snapshot?
- Why proxy candle data through the backend instead of calling Binance from every browser?
- Why does gold default to TradingView while retaining a server-proxied fallback?
- Why should translation be lazy and cached?
- How would Redis replace the in-memory cache in a multi-server deployment?
