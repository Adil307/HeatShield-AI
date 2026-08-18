from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    fortyguard_api_key: str = ""
    fortyguard_base_url: str = "https://api.fortyguard.com"
    fortyguard_request_timeout_seconds: float = 60.0
    fortyguard_poll_interval_seconds: float = 5.0
    fortyguard_max_poll_seconds: float = 180.0

    overpass_base_url: str = "https://overpass-api.de/api/interpreter"
    overpass_fallback_url: str = "https://overpass.private.coffee/api/interpreter"
    overpass_request_timeout_seconds: float = 45.0
    overpass_user_agent: str = (
        "HeatShieldAI-Hackathon26/0.4 (+https://github.com/Adil307/Heckathon26)"
    )

    app_env: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def api_key_configured(self) -> bool:
        value = self.fortyguard_api_key.strip()
        return bool(value) and value != "replace_with_your_real_key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
