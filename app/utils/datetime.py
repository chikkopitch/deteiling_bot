from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def studio_time(value: datetime, timezone: str) -> datetime:
    source = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return source.astimezone(ZoneInfo(timezone))


def format_studio_time(value: datetime, timezone: str) -> str:
    return studio_time(value, timezone).strftime("%d.%m.%Y, %H:%M")
