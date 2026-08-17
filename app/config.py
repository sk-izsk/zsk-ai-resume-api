from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = Field(..., alias="GROQ_API_KEY")
    groq_model: str = Field("openai/gpt-oss-120b", alias="GROQ_MODEL")
    upstash_redis_rest_url: str = Field(..., alias="UPSTASH_REDIS_REST_URL")
    upstash_redis_rest_token: str = Field(..., alias="UPSTASH_REDIS_REST_TOKEN")
    portfolio_profile_url: str = Field(..., alias="PORTFOLIO_PROFILE_URL")
    portfolio_profile_path: str | None = Field(None, alias="PORTFOLIO_PROFILE_PATH")
    allowed_origins: str = Field("http://localhost:2222", alias="ALLOWED_ORIGINS")
    rate_limit_max_requests: int = Field(3, alias="RATE_LIMIT_MAX_REQUESTS")
    rate_limit_window_seconds: int = Field(3600, alias="RATE_LIMIT_WINDOW_SECONDS")
    cache_ttl_seconds: int = Field(604800, alias="CACHE_TTL_SECONDS")
    rate_limit_enabled: bool = Field(True, alias="RATE_LIMIT_ENABLED")
    cache_version: str = Field("professional-first-v2", alias="CACHE_VERSION")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
