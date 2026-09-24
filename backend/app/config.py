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
    binance_market_fallback_urls: str = (
        "https://api.binance.com,https://api-gcp.binance.com,"
        "https://api1.binance.com,https://api.binance.us"
    )
    binance_futures_url: str = "https://fapi.binance.com"
    fear_greed_url: str = "https://api.alternative.me/fng/"
    gold_api_url: str = "https://api.gold-api.com/price/XAU"
    massive_api_url: str = "https://api.massive.com"
    massive_api_key: str | None = None
    market_cache_seconds: int = 60
    gold_cache_seconds: int = 15
    history_cache_seconds: int = 300
    candle_cache_seconds: int = 2
    gold_candle_cache_seconds: int = 20
    derivatives_cache_seconds: int = 10
    database_url: str | None = None
    database_path: str = ".local/chainscope.db"
    session_secret: str = "change-this-development-secret"
    session_cookie_name: str = "chainscope_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 30
    password_reset_max_age_seconds: int = 30 * 60
    alert_check_seconds: int = 60
    background_alerts_enabled: bool = True
    public_app_url: str = "http://localhost:3100"
    brevo_api_url: str = "https://api.brevo.com/v3/smtp/email"
    brevo_api_key: str | None = None
    brevo_sender_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_security: str = "starttls"
    smtp_timeout_seconds: float = 15.0
    news_rss_url: str = "https://www.coindesk.com/arc/outboundfeeds/rss/"
    news_cache_seconds: int = 300
    google_translation_api_url: str = "https://translate.googleapis.com/translate_a/single"
    translation_api_url: str = "https://api.mymemory.translated.net/get"
    translation_cache_seconds: int = 86_400
    request_timeout_seconds: float = 10.0
    ai_api_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("postgresql://"):
                return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.database_url
        return f"sqlite:///{self.database_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
