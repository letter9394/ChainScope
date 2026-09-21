from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    chain_scope_env: str = "development"
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_demo_api_key: str | None = None
    binance_market_url: str = "https://data-api.binance.vision"
    binance_futures_url: str = "https://fapi.binance.com"
    fear_greed_url: str = "https://api.alternative.me/fng/"
    gold_api_url: str = "https://api.gold-api.com/price/XAU"
    market_cache_seconds: int = 60
    gold_cache_seconds: int = 15
    history_cache_seconds: int = 300
    derivatives_cache_seconds: int = 10
    database_path: str = ".local/chainscope.db"
    news_rss_url: str = "https://www.coindesk.com/arc/outboundfeeds/rss/"
    news_cache_seconds: int = 300
    google_translation_api_url: str = "https://translate.googleapis.com/translate_a/single"
    translation_api_url: str = "https://api.mymemory.translated.net/get"
    translation_cache_seconds: int = 86_400
    request_timeout_seconds: float = 10.0
    ai_api_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
