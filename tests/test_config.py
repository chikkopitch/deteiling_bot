from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.core.config import DatabaseSettings, Settings


BASE_SETTINGS = {
    "bot_token": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
    "database_url": "postgresql+asyncpg://user:password@localhost/database",
    "owner_telegram_id": 100,
}


def test_database_maintenance_settings_require_only_database_url() -> None:
    settings = DatabaseSettings(
        database_url="postgresql+asyncpg://user:password@localhost/database"
    )

    assert settings.owner_telegram_id is None


def test_admin_ids_are_parsed_from_comma_separated_value() -> None:
    settings = Settings(
        **BASE_SETTINGS,
        admin_telegram_ids="200, 300,200",
        _env_file=None,
    )

    assert settings.admin_telegram_ids == (200, 300)
    assert settings.privileged_telegram_ids == frozenset({100, 200, 300})


def test_default_timezone_is_moscow() -> None:
    settings = Settings(**BASE_SETTINGS, _env_file=None)

    assert settings.app_timezone == ZoneInfo("Europe/Moscow")


def test_non_asyncpg_database_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **{**BASE_SETTINGS, "database_url": "sqlite:///database.sqlite"},
            _env_file=None,
        )


def test_reminder_hours_are_parsed_and_deduplicated() -> None:
    settings = Settings(
        **BASE_SETTINGS,
        reminder_hours="2,24,2",
        _env_file=None,
    )

    assert settings.reminder_hours == (24, 2)
