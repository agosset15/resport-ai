"""Конфигурация приложения. Единственная точка чтения окружения."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _Base(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class BotSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="BOT_", env_file=".env", extra="ignore")

    token: SecretStr = SecretStr("")
    webhook_base_url: str = ""
    webhook_secret: SecretStr = SecretStr("dev-secret")
    webhook_path_prefix: str = "/webhook"
    use_polling: bool = True
    api_server_url: str = ""
    api_server_local: bool = False
    admin_tg_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    @field_validator("admin_tg_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        return value

    @property
    def webhook_path(self) -> str:
        return f"{self.webhook_path_prefix}/{self.webhook_secret.get_secret_value()}"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


class DatabaseSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    user: str = "resport"
    password: SecretStr = SecretStr("resport")
    name: str = "resport"
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 10

    @property
    def dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_dsn(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql+psycopg2://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"


class RedisSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None

    @property
    def dsn(self) -> str:
        auth = f":{self.password.get_secret_value()}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class LlmSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    provider: str = "null"  # null | anthropic | openai | dslab | gigachat
    model: str = "claude-sonnet-5"
    api_key: SecretStr = SecretStr("")
    base_url: str | None = None
    timeout_seconds: float = 8.0
    max_retries: int = 2
    max_output_tokens: int = 700
    cache_ttl_seconds: int = 3600
    classify_confidence_threshold: float = 0.6
    enabled_tasks: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["classify_complaint", "normalize_answer", "explain_step"]
    )

    @field_validator("enabled_tasks", mode="before")
    @classmethod
    def _split_tasks(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class ContentSettings(_Base):
    """Тексты и параметры, которые задаёт заказчик, а не код."""

    model_config = SettingsConfigDict(env_prefix="CONTENT_", env_file=".env", extra="ignore")

    consent_version: str = "2026-01-15"
    specialist_url: str = "https://t.me/resport_support"
    support_contact: str = "@resport_support"
    scenarios_dir: Path = PROJECT_ROOT / "core" / "scenarios" / "defs"
    default_reminder_time: str = "19:00"
    default_timezone: str = "Europe/Moscow"


class AppSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    env: str = "local"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False
    host: str = "0.0.0.0"
    port: int = 8000


class Settings:
    """Композиция настроек. Собирается один раз и раздаётся через DI."""

    def __init__(self) -> None:
        self.app = AppSettings()
        self.bot = BotSettings()
        self.db = DatabaseSettings()
        self.redis = RedisSettings()
        self.llm = LlmSettings()
        self.content = ContentSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
