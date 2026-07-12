from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.database.enums import AdminRole, AppointmentStatus, ReservationStatus
from app.database.models import (
    Admin,
    Appointment,
    AppointmentSlotReservation,
    AvailableSlot,
)
from app.services.admin_appointments import AdminAppointmentService

pytestmark = pytest.mark.asyncio


def _objects(now: datetime):
    admin = Admin(id=uuid4(), telegram_id=9001, role=AdminRole.ADMIN, is_active=True)
    slot = AvailableSlot(
        id=uuid4(),
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=1),
        is_available=False,
    )
    appointment = Appointment(
        id=uuid4(),
        user_id=uuid4(),
        service_id=uuid4(),
        slot_id=slot.id,
        scheduled_at=slot.starts_at,
        status=AppointmentStatus.WAITING_ADMIN,
    )
    reservation = AppointmentSlotReservation(
        id=uuid4(),
        appointment_id=appointment.id,
        slot_id=slot.id,
        reserved_until=None,
        status=ReservationStatus.CONFIRMED,
    )
    return admin, slot, appointment, reservation


async def test_confirmation_creates_reminders_and_history() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    admin, slot, appointment, reservation = _objects(now)
    session = AsyncMock()
    session.get = AsyncMock(return_value=slot)
    service = AdminAppointmentService(session)
    service.appointments.get_for_update = AsyncMock(return_value=appointment)
    service.reservations.get_blocking_for_appointment_for_update = AsyncMock(
        return_value=reservation
    )
    service.reminders.exists_for_type = AsyncMock(return_value=False)
    service.reminders.add = AsyncMock()
    service.history.add = AsyncMock()
    service.audit.add = AsyncMock()

    result = await service.confirm(admin, appointment.id, (24, 2), now=now)

    assert result.reminders_created == 2
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert appointment.confirmed_by_admin_id == admin.id
    assert appointment.confirmed_at == now
    assert service.reminders.add.await_count == 2
    assert service.history.add.await_args.args[0].action == "confirmed"
    assert service.audit.add.await_args.args[0].action == "appointment_confirmed"


async def test_confirmation_does_not_duplicate_existing_reminders() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    admin, slot, appointment, reservation = _objects(now)
    session = AsyncMock()
    session.get = AsyncMock(return_value=slot)
    service = AdminAppointmentService(session)
    service.appointments.get_for_update = AsyncMock(return_value=appointment)
    service.reservations.get_blocking_for_appointment_for_update = AsyncMock(
        return_value=reservation
    )
    service.reminders.exists_for_type = AsyncMock(return_value=True)
    service.reminders.add = AsyncMock()
    service.history.add = AsyncMock()
    service.audit.add = AsyncMock()

    result = await service.confirm(admin, appointment.id, (24, 2), now=now)

    assert result.reminders_created == 0
    service.reminders.add.assert_not_awaited()


async def test_rejection_frees_slot_and_cancels_reminders() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    admin, slot, appointment, reservation = _objects(now)
    session = AsyncMock()
    session.get = AsyncMock(return_value=slot)
    service = AdminAppointmentService(session)
    service.appointments.get_for_update = AsyncMock(return_value=appointment)
    service.reservations.get_blocking_for_appointment_for_update = AsyncMock(
        return_value=reservation
    )
    service.reminders.cancel_future = AsyncMock(return_value=2)
    service.history.add = AsyncMock()
    service.audit.add = AsyncMock()

    result = await service.reject(
        admin, appointment.id, "Нет свободного мастера", now=now
    )

    assert appointment.status == AppointmentStatus.REJECTED
    assert appointment.rejection_reason == "Нет свободного мастера"
    assert reservation.status == ReservationStatus.CANCELLED
    assert slot.is_available is True
    assert result.reminders_cancelled == 2
    service.reminders.cancel_future.assert_awaited_once_with(appointment.id, now)
    assert service.history.add.await_args.args[0].action == "rejected"
