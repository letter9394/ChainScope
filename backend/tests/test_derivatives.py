import pytest

import app.services.derivatives as derivatives_service
from app.config import Settings
from app.services.derivatives import get_derivatives_snapshot


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, path, params=None):
        if path == "/fapi/v1/premiumIndex":
            return FakeResponse({
                "lastFundingRate": "0.0001",
                "markPrice": "65000",
                "nextFundingTime": 1_789_977_600_000,
            })
        if path == "/futures/data/openInterestHist":
            return FakeResponse([
                {"sumOpenInterestValue": "1000000"},
                {"sumOpenInterestValue": "1100000"},
            ])
        if path == "/futures/data/globalLongShortAccountRatio":
            return FakeResponse([{
                "longShortRatio": "1.5",
                "longAccount": "0.6",
                "shortAccount": "0.4",
            }])
        return FakeResponse({"data": [{"value": "70", "value_classification": "Greed"}]})


@pytest.mark.anyio
async def test_derivatives_snapshot_combines_public_feeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(derivatives_service.httpx, "AsyncClient", FakeAsyncClient)
    result = await get_derivatives_snapshot(
        Settings(derivatives_cache_seconds=0),
        "bitcoin",
    )

    assert result.available is True
    assert result.funding_rate_percent == pytest.approx(0.01)
    assert result.open_interest_usd == pytest.approx(1_100_000)
    assert result.open_interest_change_5m_percent == pytest.approx(10)
    assert result.long_account_percent == pytest.approx(60)
    assert result.fear_greed_value == 70


@pytest.mark.anyio
async def test_derivatives_snapshot_rejects_gold() -> None:
    with pytest.raises(ValueError, match="Unsupported derivatives asset"):
        await get_derivatives_snapshot(Settings(), "gold")
