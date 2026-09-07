"""Application configuration using Pydantic BaseSettings."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Application
    APP_NAME: str = "Trademark Registration System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    PUBLIC_SIGNUP_ENABLED: bool = False
    PUBLIC_APP_URL: str = "https://registr-ai.ru"
    SMTP_HOST: str = ""
    SMTP_PORT: int = Field(default=465, ge=1, le=65535)
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_SSL: bool = True
    SIGNUP_DAILY_EMAIL_LIMIT: int = Field(default=5, ge=1)
    SIGNUP_HOURLY_IP_LIMIT: int = Field(default=10, ge=1)
    SIGNUP_DAILY_GLOBAL_LIMIT: int = Field(default=100, ge=1)
    API_DOCS_ENABLED: bool = True
    ALLOWED_HOSTS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["*"]
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./trademark.db"

    # Redis (optional for MVP)
    REDIS_URL: Optional[str] = None

    # Фоновый правовой анализ. В разработке API может держать встроенный
    # worker; в production API только ставит задания в БД, а отдельный процесс
    # запускается командой ``python -m app.workers.full_analysis``.
    ANALYSIS_WORKER_MODE: str = "embedded"  # embedded | external | disabled
    ANALYSIS_WORKER_CONCURRENCY: int = 1
    ANALYSIS_WORKER_POLL_SECONDS: float = 1.0
    ANALYSIS_JOB_LEASE_SECONDS: int = 180
    ANALYSIS_JOB_HEARTBEAT_SECONDS: int = 30
    WORKER_HEARTBEAT_PATH: str = "/tmp/registr-worker.json"
    WORKER_HEARTBEAT_MAX_AGE: int = Field(default=60, ge=10)
    QUEUE_MAX_WAIT_SECONDS: int = Field(default=1800, ge=60)

    # Vector Store (optional for MVP)
    VECTOR_STORE_URL: Optional[str] = None

    # LLM Provider
    LLM_PROVIDER: str = "mock"  # local / openai / gigachat / anthropic / mock
    LLM_MODEL: str = "gpt-4o"
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    # Если основная OpenAI-совместимая модель недоступна, не вернула финальный
    # ответ или отдала невалидную структуру, текстовые проверки повторяются
    # через GigaChat. Резерв включается только при наличии Authorization Key.
    LLM_FALLBACK_ENABLED: bool = True
    # Юридический анализ требует больше времени, чем короткий чат: reasoning-модель
    # должна успеть сформировать итоговый JSON, а резервная — полноценно повторить
    # проверку, если основной ответ оказался непригодным.
    # DeepSeek на RouterAI иногда тратит больше минуты на reasoning до JSON.
    # Не переключаемся на резерв, пока не дали основной модели реальный шанс
    # завершить развёрнутую правовую проверку.
    LLM_PRIMARY_ATTEMPT_TIMEOUT: float = 180.0
    LLM_FALLBACK_ATTEMPT_TIMEOUT: float = 75.0
    LLM_HTTP_TIMEOUT: float = 210.0
    # Отдельную мультимодальную модель используем только для анализа загруженного
    # изображения обозначения. Основная текстовая модель может не принимать картинки.
    VISION_MODEL: Optional[str] = "google/gemini-2.5-flash"
    GIGACHAT_AUTHORIZATION_KEY: Optional[str] = None
    GIGACHAT_MODEL: str = "GigaChat-3-Ultra"
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    GIGACHAT_AUTH_URL: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    GIGACHAT_VERIFY_SSL: bool = True
    # GigaChat uses the certificate chain of the National Certification
    # Authority of the Russian Ministry of Digital Development.  Keep TLS
    # verification enabled and trust the bundled official root instead of
    # falling back to verify_ssl=False in production.
    GIGACHAT_CA_BUNDLE_FILE: Optional[str] = (
        "./certs/russian_trusted_root_ca_pem.crt"
    )
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
    STORAGE_MIN_FREE_MB: int = Field(default=512, ge=0)
    USER_STORAGE_MB: int = Field(default=250, ge=1)
    USER_MAX_DOCUMENTS: int = Field(default=200, ge=1)
    USER_MAX_APPLICATIONS: int = Field(default=100, ge=1)
    USER_MAX_ACTIVE_JOBS: int = Field(default=2, ge=1)
    GLOBAL_MAX_ACTIVE_JOBS: int = Field(default=20, ge=1)
    LLM_DAILY_USER_BUDGET: int = Field(default=2_000_000, ge=1)
    LLM_DAILY_GLOBAL_BUDGET: int = Field(default=10_000_000, ge=1)
    LLM_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=4)
    DOCUMENT_MAX_PAGES: int = Field(default=50, ge=1)
    DOCUMENT_MAX_EXPANDED_MB: int = Field(default=64, ge=1)
    DOCUMENT_PARSE_TIMEOUT: int = Field(default=120, ge=1)
    DOCUMENT_PARSE_MEMORY_MB: int = Field(default=768, ge=128)

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
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    @model_validator(mode="after")
    def validate_server_security(self):
        if self.ENVIRONMENT.lower() == "production" or self.ANALYSIS_WORKER_MODE == "external":
            key = self.SECRET_KEY
            if (len(key.encode("utf-8")) < 32 or len(set(key)) < 12
                    or any(marker in key.lower() for marker in
                           ("change-me", "replace", "example", "placeholder", "secret-key"))):
                raise ValueError("Server profile requires a separate random SECRET_KEY (at least 32 bytes)")
            if self.DEBUG:
                raise ValueError("DEBUG must be disabled in the server profile")
        return self

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return list(v)  # type: ignore[arg-type]

    @field_validator(
        "ALLOWED_HOSTS",
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

    @field_validator("ANALYSIS_WORKER_MODE")
    @classmethod
    def validate_analysis_worker_mode(cls, v: str) -> str:
        value = v.strip().lower()
        if value not in {"embedded", "external", "disabled"}:
            raise ValueError(
                "ANALYSIS_WORKER_MODE must be embedded, external or disabled"
            )
        return value


settings = Settings()
