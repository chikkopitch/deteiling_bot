from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=True, enable_decoding=False
    )

    BOT_TOKEN: str = Field(min_length=10)
    ADMIN_IDS: tuple[int, ...]
    MANAGER_USERNAME: str
    MANAGER_IDS: tuple[int, ...] = ()
    DATABASE_URL: str
    REDIS_URL: str | None = None
    STUDIO_TIMEZONE: str = "Asia/Yekaterinburg"
    STUDIO_NAME: str
    STUDIO_ADDRESS: str
    SUPPORT_PHONE: str
    REMINDER_HOURS_BEFORE: tuple[int, ...] = (24, 2)
    MAX_PHOTOS_PER_BOOKING: int = Field(default=6, ge=0, le=20)
    MAX_PHOTO_SIZE_MB: int = Field(default=10, ge=1, le=20)
    SLOT_HOLD_MINUTES: int = Field(default=10, ge=1, le=60)
    MIN_RESCHEDULE_HOURS: int = Field(default=2, ge=0, le=168)
    BOOKING_HORIZON_DAYS: int = Field(default=30, ge=1, le=365)
    LOG_LEVEL: str = "INFO"
    MAP_URL: str | None = None

    @field_validator("ADMIN_IDS", "MANAGER_IDS", "REMINDER_HOURS_BEFORE", mode="before")
    @classmethod
    def parse_csv_ints(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(int(item.strip()) for item in value.split(",") if item.strip())
        return value

    @field_validator("STUDIO_TIMEZONE")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("STUDIO_TIMEZONE must be a valid IANA timezone") from error
        return value

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL has an unsupported value")
        return level


@lru_cache
def get_settings() -> Settings:
    return Settings()
