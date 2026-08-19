from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import BACKEND_ROOT


class Settings(BaseSettings):
    fortyguard_api_key: str = ""
    fortyguard_base_url: str = "https://api.fortyguard.com"
    fortyguard_request_timeout_seconds: float = 60.0
    fortyguard_poll_interval_seconds: float = 5.0
    fortyguard_max_poll_seconds: float = 180.0

    overpass_base_url: str = "https://overpass-api.de/api/interpreter"
    overpass_fallback_url: str = "https://overpass.private.coffee/api/interpreter"
    overpass_third_url: str = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    overpass_request_timeout_seconds: float = 55.0
    overpass_connect_timeout_seconds: float = 12.0
    overpass_user_agent: str = (
        "HeatShieldAI-Hackathon26/0.4.2 (+https://github.com/Adil307/Heckathon26)"
    )

    # Grounded Copilot. Deterministic remains the fail-safe zero-cost default.
    # Supported providers: deterministic, ollama, openai.
    copilot_provider: str = "deterministic"
    copilot_model: str = "gpt-5.6"
    copilot_timeout_seconds: float = 30.0
    copilot_max_output_tokens: int = 500
    openai_api_key: str = ""

    # Local Qwen planner through Ollama. No API key is required for localhost.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"
    ollama_timeout_seconds: float = 180.0
    ollama_keep_alive: str = "10m"

    app_env: str = "development"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def api_key_configured(self) -> bool:
        value = self.fortyguard_api_key.strip()
        return bool(value) and value != "replace_with_your_real_key"

    @property
    def openai_api_key_configured(self) -> bool:
        value = self.openai_api_key.strip()
        return bool(value) and value != "replace_with_your_openai_key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
