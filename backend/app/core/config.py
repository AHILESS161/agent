"""Application configuration using Pydantic BaseSettings."""

from __future__ import annotations

from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Trademark Registration System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./trademark.db"

    # Redis (optional for MVP)
    REDIS_URL: Optional[str] = None

    # Vector Store (optional for MVP)
    VECTOR_STORE_URL: Optional[str] = None

    # LLM Provider
    LLM_PROVIDER: str = "mock"  # local / openai / anthropic / mock
    LLM_MODEL: str = "gpt-4o"
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None

    # Провайдер реестра товарных знаков (Роспатент / ФИПС).
    # На текущем этапе реально доступен только "mock" — демо-датасет.
    FIPS_PROVIDER: str = "mock"

    # Security
    SECRET_KEY: str = "change-me-in-production-use-secrets-token-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Файловое хранилище оригиналов документов
    FILE_STORAGE_PATH: str = "./storage/documents"
    MAX_UPLOAD_MB: int = 25

    # Logging
    LOG_LEVEL: str = "INFO"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return list(v)  # type: ignore[arg-type]

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return upper


settings = Settings()
