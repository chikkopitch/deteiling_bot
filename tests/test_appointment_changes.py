from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import (
    Appointment,
    AppointmentSlotReservation,
    AvailableSlot,
    User,
)
from app.services.appointment_changes import AppointmentChangeService
from app.services.schedule import SlotUnavailableError
from app.services.vehicle_selection import VehicleSelectionError

pytestmark = pytest.mark.asyncio


def _data(now):
    user = User(id=uuid4(), telegram_id=1)
    old = AvailableSlot(
        id=uuid4(),
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=1),
        is_available=False,
    )
    new = AvailableSlot(
        id=uuid4(),
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=1),
        is_available=False,
    )
    appointment = Appointment(
        id=uuid4(),
        user_id=user.id,
        slot_id=old.id,
        scheduled_at=old.starts_at,
        status=AppointmentStatus.CONFIRMED,
    )
    old_res = AppointmentSlotReservation(
        id=uuid4(),
        appointment_id=appointment.id,
        slot_id=old.id,
        status=ReservationStatus.CONFIRMED,
    )
    new_res = AppointmentSlotReservation(
        id=uuid4(),
        appointment_id=appointment.id,
        slot_id=new.id,
        status=ReservationStatus.ACTIVE,
        reserved_until=now + timedelta(minutes=10),
    )
    return user, old, new, appointment, old_res, new_res


async def test_confirm_reschedule_switches_slots_and_reminders() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    user, old, new, appointment, old_res, new_res = _data(now)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[new, old])
    service = AppointmentChangeService(
        session, deadline_hours=3, reservation_minutes=15
    )
    service.appointments.get_for_update = AsyncMock(return_value=appointment)
    service.reservations.get_for_appointment_by_status_for_update = AsyncMock(
        side_effect=[old_res, new_res]
    )
    service.reservations.get_blocking_for_slot_for_update = AsyncMock(
        return_value=new_res
    )
    service.slots.get_for_update = AsyncMock(side_effect=[new, old])
    service.reminders.cancel_open = AsyncMock(return_value=2)
    service.reminders.add = AsyncMock()
    service.history.add = AsyncMock()

    await service.confirm_reschedule(
        user, appointment.id, reminder_hours=(24, 2), now=now
    )

    assert appointment.slot_id == new.id
    assert appointment.scheduled_at == new.starts_at
    assert old_res.status == ReservationStatus.CANCELLED
    assert new_res.status == ReservationStatus.CONFIRMED
    assert old.is_available is True
    assert service.reminders.add.await_count == 2
    assert service.history.add.await_args.args[0].action == "rescheduled"


async def test_lost_new_slot_preserves_old_appointment() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    user, old, new, appointment, old_res, new_res = _data(now)
    new_res.reserved_until = now - timedelta(seconds=1)
    service = AppointmentChangeService(
        AsyncMock(), deadline_hours=3, reservation_minutes=15
    )
    service.appointments.get_for_update = AsyncMock(return_value=appointment)
    service.reservations.get_for_appointment_by_status_for_update = AsyncMock(
        side_effect=[old_res, new_res]
    )
    service.slots.get_for_update = AsyncMock(return_value=new)

    with pytest.raises(SlotUnavailableError):
        await service.confirm_reschedule(
            user, appointment.id, reminder_hours=(24, 2), now=now
        )
    assert appointment.slot_id == old.id
    assert old_res.status == ReservationStatus.CONFIRMED


async def test_user_cancellation_releases_everything() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    user, old, _, appointment, old_res, _ = _data(now)
    session = AsyncMock()
    service = AppointmentChangeService(
        session, deadline_hours=3, reservation_minutes=15
    )
    service.appointments.get_for_update = AsyncMock(return_value=appointment)
    service.reservations.get_for_appointment_by_status_for_update = AsyncMock(
        side_effect=[old_res, None]
    )
    service.slots.get_for_update = AsyncMock(return_value=old)
    service.reminders.cancel_open = AsyncMock(return_value=2)
    service.history.add = AsyncMock()

    status = await service.cancel(user, appointment.id, "Изменились планы", now=now)
    assert status == AppointmentStatus.CANCELLED_BY_USER
    assert appointment.cancelled_at == now
    assert old_res.status == ReservationStatus.CANCELLED
    assert old.is_available is True
    service.reminders.cancel_open.assert_awaited_once()


async def test_deadline_blocks_user_but_admin_can_bypass() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    user, _, _, appointment, _, _ = _data(now)
    appointment.scheduled_at = now + timedelta(hours=2)
    service = AppointmentChangeService(
        AsyncMock(), deadline_hours=3, reservation_minutes=15
    )
    with pytest.raises(VehicleSelectionError, match="менеджером"):
        service._check_change_allowed(appointment, now, bypass_deadline=False)
    service._check_change_allowed(appointment, now, bypass_deadline=True)
