# ChainScope learning notes

## Why the project is split into frontend and backend

The browser is responsible for interaction and visualization. FastAPI owns external API calls and risk calculations. This separation prevents private API keys and business rules from being exposed in browser code, and it lets each side be tested independently.

## How a market request flows

1. The Next.js page requests `/api/markets` from FastAPI.
2. FastAPI checks its short-lived cache.
3. On a cache miss, the CoinGecko client requests fresh market data.
4. The response is validated with Pydantic models.
5. The browser renders the normalized result.

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
- How would Redis replace the in-memory cache in a multi-server deployment?
