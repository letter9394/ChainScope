from typing import Literal

from pydantic import BaseModel, Field


class MarketCoin(BaseModel):
    id: str
    symbol: str
    name: str
    image: str | None = None
    current_price: float
    market_cap: float | None = None
    total_volume: float | None = None
    price_change_percentage_24h: float | None = None
    price_change_percentage_7d: float | None = None
    last_updated: str | None = None
    sparkline: list[float] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    timestamp: int
    price: float
    volume: float | None = None


class RiskMetric(BaseModel):
    key: str
    label: str
    value: float
    display_value: str
    contribution: int
    explanation: str


class RiskAssessment(BaseModel):
    coin_id: str
    symbol: str
    score: int = Field(ge=0, le=100)
    level: Literal["low", "medium", "high"]
    level_label: str
    summary: str
    metrics: list[RiskMetric]
    sample_days: int
    calculated_at: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    market_provider: str


class NewsArticle(BaseModel):
    id: str
    title: str
    url: str
    source: str
    published_at: str
    image_url: str | None = None
    summary: str
    sentiment: Literal["positive", "neutral", "negative"]
    sentiment_label: str
    related_symbols: list[str] = Field(default_factory=list)
    analysis_mode: Literal["rules", "ai"]


class NewsResponse(BaseModel):
    articles: list[NewsArticle]
    analysis_mode: Literal["rules", "ai"]
    notice: str


class WatchlistItem(BaseModel):
    coin_id: str
    symbol: str
    added_at: str
