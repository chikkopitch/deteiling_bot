from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingStatus,
    Notification,
    NotificationStatus,
    SlotStatus,
    TimeSlot,
    User,
    Vehicle,
)
from app.scheduler import NotificationWorker
from app.services import BookingService


async def test_reminders_are_idempotent_and_cancelled_with_booking(session: AsyncSession) -> None:
    user = User(telegram_id=901, first_name="A")
    starts_at = datetime.now(UTC) + timedelta(days=3)
    slot = TimeSlot(
        starts_at=starts_at, ends_at=starts_at + timedelta(hours=1), status=SlotStatus.BOOKED
    )
    session.add_all([user, slot])
    await session.flush()
    vehicle = Vehicle(
        user_id=user.id, brand_name="BMW", model_name="X5", year=2022, vehicle_class="SUV"
    )
    session.add(vehicle)
    await session.flush()
    booking = Booking(
        user_id=user.id,
        vehicle_id=vehicle.id,
        slot_id=slot.id,
        status=BookingStatus.PENDING,
    )
    session.add(booking)
    await session.commit()

    service = BookingService(session)
    await service.confirm(booking.id, user.id, (24, 2))
    await service.confirm(booking.id, user.id, (24, 2))
    reminders = list(
        await session.scalars(select(Notification).where(Notification.booking_id == booking.id))
    )
    assert len(reminders) == 2

    await service.change_status(booking.id, BookingStatus.CANCELLED_BY_CLIENT, user.id)
    reminders = list(
        await session.scalars(select(Notification).where(Notification.booking_id == booking.id))
    )
    assert all(item.status == NotificationStatus.CANCELLED for item in reminders)


def test_notification_retry_is_limited() -> None:
    worker = NotificationWorker.__new__(NotificationWorker)
    worker.max_attempts = 2
    note = Notification(
        booking_id=uuid4(),
        user_id=uuid4(),
        type="reminder",
        scheduled_at=datetime.now(UTC),
        idempotency_key="retry-test",
        attempts=0,
        status=NotificationStatus.PENDING,
    )

    worker._retry(note, None, "network")
    assert note.status == NotificationStatus.RETRY and note.attempts == 1
    worker._retry(note, None, "network")
    assert note.status == NotificationStatus.FAILED and note.attempts == 2
