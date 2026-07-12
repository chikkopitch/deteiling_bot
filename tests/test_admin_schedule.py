from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.database.enums import AdminRole
from app.database.models import Admin, AvailableSlot
from app.services.admin_schedule import (
    AdminScheduleError,
    AdminScheduleService,
    parse_slot_drafts,
)


def test_parse_slot_drafts_converts_local_time_to_utc() -> None:
    drafts = parse_slot_drafts(
        "15.07.2026 10:00 120\n15.07.2026 13:00 60",
        timezone=ZoneInfo("Europe/Moscow"),
        booking_days_ahead=30,
        now=datetime(2026, 7, 12, 8, tzinfo=UTC),
    )

    assert len(drafts) == 2
    assert drafts[0].starts_at == datetime(2026, 7, 15, 7, tzinfo=UTC)
    assert drafts[0].ends_at == datetime(2026, 7, 15, 9, tzinfo=UTC)


def test_parse_slot_drafts_rejects_overlapping_lines() -> None:
    with pytest.raises(AdminScheduleError, match="пересекаются"):
        parse_slot_drafts(
            "15.07.2026 10:00 120\n15.07.2026 11:00 60",
            timezone=ZoneInfo("Europe/Moscow"),
            booking_days_ahead=30,
            now=datetime(2026, 7, 12, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_create_slots_adds_slots_and_audit_entries() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = Mock()
    admin = Admin(id=uuid4(), telegram_id=1, role=AdminRole.OWNER, is_active=True)
    drafts = parse_slot_drafts(
        "15.07.2026 10:00 120\n15.07.2026 13:00 60",
        timezone=ZoneInfo("Europe/Moscow"),
        booking_days_ahead=30,
        now=datetime(2026, 7, 12, 8, tzinfo=UTC),
    )

    slots = await AdminScheduleService(session).create_slots(admin, drafts)

    assert len(slots) == 2
    assert all(slot.is_available for slot in slots)
    assert session.add.call_count == 4
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_slot_blocks_slot_without_deleting_history() -> None:
    now = datetime.now(UTC)
    slot = AvailableSlot(
        id=uuid4(),
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=1),
        is_available=True,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=slot)
    session.scalar = AsyncMock(return_value=None)
    session.add = Mock()
    admin = Admin(id=uuid4(), telegram_id=1, role=AdminRole.OWNER, is_active=True)

    result = await AdminScheduleService(session).close_slot(admin, slot.id)

    assert result is slot
    assert slot.is_available is False
    assert slot.blocked_reason == "Закрыт администратором"
    assert session.add.call_count == 1
    session.flush.assert_awaited_once()
