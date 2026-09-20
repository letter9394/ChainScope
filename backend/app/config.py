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
    market_cache_seconds: int = 60
    history_cache_seconds: int = 300
    database_path: str = ".local/chainscope.db"
    news_rss_url: str = "https://www.coindesk.com/arc/outboundfeeds/rss/"
    news_cache_seconds: int = 300
    request_timeout_seconds: float = 10.0
    ai_api_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
