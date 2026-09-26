from fastapi.testclient import TestClient

from app.main import app, get_database, get_market_client
from app.models import CandlePoint, CandleSeries, DerivativesSnapshot, HistoryPoint, MarketCoin, NewsResponse


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

    async def get_candles(
        self,
        asset_id: str,
        interval: str,
        limit: int,
        source: str = "auto",
    ) -> CandleSeries:
        if asset_id not in {"bitcoin", "ethereum", "solana", "gold"}:
            raise ValueError(f"Unsupported asset: {asset_id}")
        return CandleSeries(
            asset_id=asset_id,
            symbol="PAXGUSDT" if asset_id == "gold" else "BTCUSDT",
            display_symbol="PAXG/USDT" if asset_id == "gold" else "BTC/USDT",
            interval=interval,
            provider="Binance Spot",
            is_proxy=asset_id == "gold",
            proxy_notice="proxy" if asset_id == "gold" else None,
            updated_at="2026-09-23T00:00:00+00:00",
            candles=[
                CandlePoint(time=1_700_000_000, open=100, high=105, low=98, close=103, volume=42),
                CandlePoint(time=1_700_000_060, open=103, high=106, low=101, close=104, volume=51),
            ],
        )


app.dependency_overrides[get_market_client] = lambda: FakeMarketClient()
client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["database"]["status"] == "ok"
    assert response.json()["checks"]["scheduler"]["status"] in {"starting", "ok"}
    assert response.json()["checks"]["scheduler"]["interval_seconds"] >= 15
    assert "last_evaluated_users" in response.json()["checks"]["scheduler"]
    assert response.json()["checked_at"]
    assert response.json()["uptime_seconds"] >= 0
    assert response.headers["x-request-id"]


def test_health_endpoint_reports_database_failure_without_leaking_connection_details() -> None:
    class BrokenDatabase:
        def ping(self) -> None:
            raise RuntimeError("postgresql://secret-user:secret-password@example.invalid/db")

    app.dependency_overrides[get_database] = lambda: BrokenDatabase()
    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    database_check = response.json()["checks"]["database"]
    assert database_check["status"] == "error"
    assert "RuntimeError" in database_check["detail"]
    assert "secret-password" not in response.text


def test_request_id_is_preserved_for_safe_values() -> None:
    response = client.get("/api/markets", headers={"X-Request-ID": "e2e-request-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "e2e-request-123"


def test_markets_endpoint() -> None:
    response = client.get("/api/markets")

    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "BTC"


def test_candles_endpoint_returns_same_origin_chart_data() -> None:
    response = client.get("/api/assets/gold/candles?interval=15m&limit=300")

    assert response.status_code == 200
    assert response.json()["display_symbol"] == "PAXG/USDT"
    assert response.json()["is_proxy"] is True
    assert len(response.json()["candles"]) == 2


def test_candles_endpoint_accepts_two_point_incremental_request() -> None:
    response = client.get("/api/assets/bitcoin/candles?interval=1m&limit=2")

    assert response.status_code == 200
    assert len(response.json()["candles"]) == 2


def test_candles_endpoint_accepts_realtime_gold_proxy_source() -> None:
    response = client.get("/api/assets/gold/candles?interval=1m&limit=300&source=proxy")

    assert response.status_code == 200
    assert response.json()["is_proxy"] is True


def test_candles_endpoint_rejects_unknown_source() -> None:
    response = client.get("/api/assets/gold/candles?source=unknown")

    assert response.status_code == 422


def test_candles_endpoint_rejects_unknown_asset() -> None:
    response = client.get("/api/assets/dogecoin/candles?interval=15m&limit=300")

    assert response.status_code == 404


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


def test_risk_backtest_endpoint_returns_horizon_statistics() -> None:
    response = client.get("/api/coins/bitcoin/risk/backtest?days=365")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "BTC"
    assert body["risk_threshold"] == 60
    assert body["hit_threshold_percent"] == 3.0
    assert [item["horizon_days"] for item in body["horizons"]] == [1, 3, 7]


def test_risk_backtest_endpoint_rejects_unknown_coin() -> None:
    response = client.get("/api/coins/dogecoin/risk/backtest?days=365")

    assert response.status_code == 404
