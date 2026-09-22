from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./stratum.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-this-secret-before-deploying"
    session_minutes: int = 60
    redis_required: bool = False
    # Optional private model gateway. Receives incident evidence, never credentials.
    triage_model_url: str = ""
    triage_model_key: str = ""
    triage_model_name: str = ""

    @model_validator(mode="after")
    def production_defaults(self):
        if self.environment == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("development-"):
                raise ValueError(
                    "Production requires a unique JWT_SECRET of at least 32 characters"
                )
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("Production requires PostgreSQL")
            self.redis_required = True
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
