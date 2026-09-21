from fastapi.testclient import TestClient

from app.main import app, get_market_client
from app.models import DerivativesSnapshot, HistoryPoint, MarketCoin, NewsResponse


class FakeMarketClient:
    async def get_markets(self) -> list[MarketCoin]:
        return [
            MarketCoin(
                id="bitcoin",
                symbol="BTC",
                name="Bitcoin",
                current_price=65_000,
                sparkline=[64_000, 65_000],
            )
        ]

    async def get_history(self, coin_id: str, days: int) -> list[HistoryPoint]:
        if coin_id not in {"bitcoin", "ethereum", "solana"}:
            raise ValueError(f"Unsupported coin: {coin_id}")
        return [
            HistoryPoint(timestamp=index * 86_400_000, price=100 + index, volume=1_000)
            for index in range(max(8, days))
        ]


app.dependency_overrides[get_market_client] = lambda: FakeMarketClient()
client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_markets_endpoint() -> None:
    response = client.get("/api/markets")

    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "BTC"


def test_history_endpoint_validates_days() -> None:
    response = client.get("/api/coins/bitcoin/history?days=2")

    assert response.status_code == 422


def test_history_endpoint_returns_points() -> None:
    response = client.get("/api/coins/ethereum/history?days=7")

    assert response.status_code == 200
    assert len(response.json()) == 8


def test_risk_endpoint_is_explainable(monkeypatch) -> None:
    async def fake_derivatives(*args, **kwargs) -> DerivativesSnapshot:
        return DerivativesSnapshot(
            coin_id="solana",
            symbol="SOL",
            available=False,
            updated_at="2026-09-21T00:00:00+00:00",
            source="test",
        )

    async def fake_news(*args, **kwargs) -> NewsResponse:
        return NewsResponse(articles=[], analysis_mode="rules", notice="test")

    monkeypatch.setattr("app.main.get_derivatives_snapshot", fake_derivatives)
    monkeypatch.setattr("app.main.get_news", fake_news)
    response = client.get("/api/coins/solana/risk?days=30")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "SOL"
    assert len(body["metrics"]) == 4
    assert body["summary"]


def test_unknown_coin_returns_404() -> None:
    response = client.get("/api/coins/dogecoin/risk?days=30")

    assert response.status_code == 404
