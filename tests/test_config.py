import pytest
from pydantic import ValidationError

from app.config import Settings

BASE = {
    "BOT_TOKEN": "123456:abcdefghij",
    "ADMIN_IDS": "1,2",
    "MANAGER_USERNAME": "manager",
    "DATABASE_URL": "postgresql+asyncpg://u:p@db/x",
    "REDIS_URL": "redis://redis/0",
    "STUDIO_NAME": "Studio",
    "STUDIO_ADDRESS": "Address",
    "SUPPORT_PHONE": "+79990000000",
}


def test_settings_parse_lists() -> None:
    settings = Settings(**BASE)
    assert settings.ADMIN_IDS == (1, 2)
    assert settings.REMINDER_HOURS_BEFORE == (24, 2)


def test_invalid_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, STUDIO_TIMEZONE="Wrong/Timezone")


def test_missing_required_configuration_is_rejected() -> None:
    incomplete = dict(BASE)
    incomplete.pop("BOT_TOKEN")
    with pytest.raises(ValidationError, match="BOT_TOKEN"):
        Settings(**incomplete)
