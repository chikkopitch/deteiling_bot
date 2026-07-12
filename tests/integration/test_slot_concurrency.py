from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.enums import AppointmentStatus
from app.database.models import Appointment, AvailableSlot, ConversationState, User
from app.services.schedule import ScheduleService, SlotUnavailableError

pytestmark = pytest.mark.asyncio


async def test_two_users_can_create_only_one_reservation(
    postgres_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    users = [User(telegram_id=7_000_000_001), User(telegram_id=7_000_000_002)]
    slot = AvailableSlot(
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=1),
        is_available=True,
    )
    postgres_session.add_all([*users, slot])
    await postgres_session.flush()
    appointments = [
        Appointment(user_id=user.id, status=AppointmentStatus.DRAFT) for user in users
    ]
    postgres_session.add_all(appointments)
    await postgres_session.flush()
    postgres_session.add_all(
        [
            ConversationState(
                user_id=user.id,
                flow="booking",
                step="date_selection",
                payload={"appointment_id": str(appointment.id)},
                expires_at=now + timedelta(days=1),
            )
            for user, appointment in zip(users, appointments, strict=True)
        ]
    )
    await postgres_session.commit()

    factory = async_sessionmaker(
        postgres_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def try_reserve(user: User) -> bool:
        async with factory() as session:
            try:
                async with session.begin():
                    service = ScheduleService(
                        session,
                        timezone=UTC,
                        booking_days_ahead=30,
                        reservation_minutes=15,
                    )
                    await service.reserve(user, slot.id, now=now)
                return True
            except SlotUnavailableError:
                return False

    results = await asyncio.gather(*(try_reserve(user) for user in users))

    assert sorted(results) == [False, True]
