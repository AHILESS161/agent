"""Application configuration using Pydantic BaseSettings."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    LLM_PROVIDER: str = "mock"  # local / openai / gigachat / anthropic / mock
    LLM_MODEL: str = "gpt-4o"
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    GIGACHAT_AUTHORIZATION_KEY: Optional[str] = None
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    GIGACHAT_AUTH_URL: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    GIGACHAT_VERIFY_SSL: bool = True
    GIGACHAT_CA_BUNDLE_FILE: Optional[str] = None
    GIGACHAT_MIN_REQUEST_INTERVAL: float = 1.25
    GIGACHAT_MAX_RETRIES: int = 5

    # Провайдер реестра товарных знаков (Роспатент / ФИПС).
    FIPS_PROVIDER: str = "mock"
    FIPS_BASE_URL: str = "https://searchplatform.rospatent.gov.ru/patsearch/v0.2/"
    FIPS_API_KEY: Optional[str] = None
    FIPS_TRADEMARK_DATASETS: Annotated[List[str], NoDecode] = Field(
        default_factory=list
    )
    FIPS_APPLICATION_DATASETS: Annotated[List[str], NoDecode] = Field(
        default_factory=list
    )
    FIPS_CLASS_FILTER_FIELD: str = "classification.icgs"
    FIPS_TIMEOUT: float = 30.0
    FIPS_VERIFY_SSL: bool = True
    FIPS_PUBLIC_BASE_URL: str = "https://searchplatform.rospatent.gov.ru/"
    FIPS_PUBLIC_DATA_SOURCES: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [
            "trademarks",
            "known_trademarks",
            "international_trademarks",
        ]
    )
    FIPS_PUBLIC_MAX_RESULTS: int = 100
    FIPS_PUBLIC_PAGE_SIZE: int = 50
    FIPS_PUBLIC_MIN_INTERVAL: float = 0.75

    # --- Feature flags ---------------------------------------------------
    # Фактическая подача заявки во внешний реестр. Выключена намеренно:
    # подача — юридически значимое действие, она требует отдельного
    # осознанного включения и подтверждения специалистом, а не должна
    # выполняться попутно в общем прогоне пайплайна.
    ENABLE_REAL_SUBMISSION: bool = False

    # Демо-режим: запрещает любые реальные внешние действия
    # (подачу заявки, отправку писем, изменение внешних систем).
    DEMO_MODE: bool = True

    # Security
    SECRET_KEY: str = "change-me-in-production-use-secrets-token-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Ограничение частоты запросов (защита от подбора пароля и
    # исчерпания дискового пространства загрузками).
    RATE_LIMIT_ENABLED: bool = True

    # Файловое хранилище оригиналов документов
    FILE_STORAGE_PATH: str = "./storage/documents"
    MAX_UPLOAD_MB: int = 25

    # OCR для сканов и изображений. Обычный PDF с текстовым слоем проходит
    # без OCR; Tesseract запускается только для страниц, где текста нет.
    OCR_ENABLED: bool = True
    OCR_LANGUAGES: str = "rus+eng"
    OCR_DPI: int = 300
    OCR_PSM: int = 3
    OCR_MIN_TEXT_CHARS: int = 30
    OCR_TIMEOUT_SECONDS: int = 60
    OCR_MAX_IMAGE_PIXELS: int = 40_000_000
    OCR_TESSERACT_CMD: Optional[str] = None
    OCR_TESSDATA_DIR: Optional[str] = None

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

    @field_validator(
        "FIPS_TRADEMARK_DATASETS",
        "FIPS_APPLICATION_DATASETS",
        "FIPS_PUBLIC_DATA_SOURCES",
        mode="before",
    )
    @classmethod
    def parse_dataset_ids(cls, v: object) -> List[str]:
        if v in (None, ""):
            return []
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return [str(item).strip() for item in v if str(item).strip()]  # type: ignore[union-attr]

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return upper


settings = Settings()
