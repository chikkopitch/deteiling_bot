from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SlotStatus, StudioSchedule, TimeSlot, User
from app.services import AvailabilityService


async def test_expired_hold_is_released(session: AsyncSession) -> None:
    user = User(telegram_id=501, first_name="A")
    point = datetime.now(UTC) + timedelta(days=1)
    slot = TimeSlot(
        starts_at=point,
        ends_at=point + timedelta(hours=1),
        status=SlotStatus.HELD,
        held_by_user_id=user.id,
        hold_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add_all([user, slot])
    await session.flush()
    slot.held_by_user_id = user.id
    await session.commit()

    released = await AvailabilityService(session, "UTC").release_expired_holds()

    await session.refresh(slot)
    assert released == 1 and slot.status == SlotStatus.AVAILABLE and slot.held_by_user_id is None


async def test_only_available_slots_are_returned(session: AsyncSession) -> None:
    point = (datetime.now(UTC) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    session.add_all(
        [
            TimeSlot(starts_at=point, ends_at=point + timedelta(hours=1)),
            TimeSlot(
                starts_at=point + timedelta(hours=1),
                ends_at=point + timedelta(hours=2),
                status=SlotStatus.BLOCKED,
            ),
        ]
    )
    await session.commit()

    service = AvailabilityService(session, "UTC")
    slots = await service.slots_for_date(point.date())
    dates = await service.dates_for_week(0, 30)

    assert [slot.status for slot in slots] == [SlotStatus.AVAILABLE]
    assert point.date() in dates


async def test_closed_schedule_excludes_otherwise_available_slot(session: AsyncSession) -> None:
    point = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    session.add_all(
        [
            TimeSlot(starts_at=point, ends_at=point + timedelta(hours=1)),
            StudioSchedule(
                weekday=point.weekday(),
                opens_at=datetime.min.time(),
                closes_at=datetime.max.time(),
                effective_date=point.date(),
                is_closed=True,
            ),
        ]
    )
    await session.commit()

    slots = await AvailabilityService(session, "UTC").slots_for_date(point.date())

    assert slots == []
