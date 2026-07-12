"""Typed application settings loaded from environment and .env."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Minimal settings used by standalone database maintenance scripts."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str
    owner_telegram_id: int | None = Field(default=None, gt=0)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must start with postgresql+asyncpg://")
        return value


class Settings(DatabaseSettings):
    """Validated runtime configuration."""

    bot_token: SecretStr = Field(min_length=20)
    owner_telegram_id: int = Field(gt=0)
    admin_telegram_ids: tuple[int, ...] = ()
    app_timezone: ZoneInfo = ZoneInfo("Europe/Moscow")
    log_level: str = "INFO"
    currency_symbol: str = Field(default="₽", min_length=1, max_length=8)
    booking_days_ahead: int = Field(default=30, ge=1, le=365)
    slot_reservation_minutes: int = Field(default=15, ge=1, le=120)
    reservation_cleanup_seconds: int = Field(default=60, ge=60, le=120)
    reminder_hours: tuple[int, ...] = (24, 2)
    reminder_check_interval_seconds: int = Field(default=60, ge=30, le=300)
    reminder_max_attempts: int = Field(default=5, ge=1, le=20)
    reminder_processing_timeout_minutes: int = Field(default=10, ge=1, le=120)
    appointment_change_deadline_hours: int = Field(default=3, ge=0, le=168)
    studio_name: str = ""
    studio_address: str = ""
    studio_phone: str = ""
    manager_telegram: str = ""

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> object:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            raw_ids = [item.strip() for item in value.split(",")]
            parsed = tuple(int(item) for item in raw_ids if item)
            if any(item <= 0 for item in parsed):
                raise ValueError("ADMIN_TELEGRAM_IDS must contain positive integers")
            return parsed
        return value

    @field_validator("admin_telegram_ids")
    @classmethod
    def deduplicate_admin_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(dict.fromkeys(value))

    @field_validator("reminder_hours", mode="before")
    @classmethod
    def parse_reminder_hours(cls, value: object) -> object:
        if isinstance(value, str):
            parsed = tuple(
                int(item.strip()) for item in value.split(",") if item.strip()
            )
            if not parsed or any(item <= 0 for item in parsed):
                raise ValueError("REMINDER_HOURS must contain positive integers")
            return parsed
        return value

    @field_validator("reminder_hours")
    @classmethod
    def normalize_reminder_hours(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(sorted(set(value), reverse=True))

    @field_validator("app_timezone", mode="before")
    @classmethod
    def parse_timezone(cls, value: object) -> ZoneInfo:
        if isinstance(value, ZoneInfo):
            return value
        try:
            return ZoneInfo(str(value))
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown IANA timezone: {value}") from error

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @property
    def privileged_telegram_ids(self) -> frozenset[int]:
        return frozenset((self.owner_telegram_id, *self.admin_telegram_ids))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Load only DATABASE_URL for maintenance commands."""
    return DatabaseSettings()
