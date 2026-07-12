from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import (
    Appointment,
    AppointmentSlotReservation,
    AvailableSlot,
    ConversationState,
    User,
)
from app.services.submission import SubmissionService, SubmissionStatus

pytestmark = pytest.mark.asyncio


def _objects(now: datetime):
    user = User(id=uuid4(), telegram_id=123123)
    slot = AvailableSlot(
        id=uuid4(),
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=1),
        is_available=False,
    )
    appointment = Appointment(
        id=uuid4(),
        user_id=user.id,
        service_id=uuid4(),
        vehicle_class_id=uuid4(),
        slot_id=slot.id,
        scheduled_at=slot.starts_at,
        customer_name="Иван",
        customer_phone="+79991234567",
        status=AppointmentStatus.DRAFT,
    )
    reservation = AppointmentSlotReservation(
        id=uuid4(),
        appointment_id=appointment.id,
        slot_id=slot.id,
        reserved_until=now + timedelta(minutes=10),
        status=ReservationStatus.ACTIVE,
    )
    state = ConversationState(
        id=uuid4(),
        user_id=user.id,
        flow="booking",
        step="review",
        payload={
            "appointment_id": str(appointment.id),
            "slot_id": str(slot.id),
            "scheduled_at": slot.starts_at.isoformat(),
            "reserved_until": reservation.reserved_until.isoformat(),
        },
        expires_at=now + timedelta(days=1),
    )
    return user, slot, appointment, reservation, state


async def test_full_submission_confirms_reservation_and_closes_state() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    user, slot, appointment, reservation, state = _objects(now)
    session = AsyncMock()
    session.get = AsyncMock(return_value=slot)
    service = SubmissionService(session)
    service.states.get_active_for_flow = AsyncMock(return_value=state)
    service.reservations.get_blocking_for_appointment_for_update = AsyncMock(
        return_value=reservation
    )
    service.reservations.get_blocking_for_slot_for_update = AsyncMock(
        return_value=reservation
    )
    service.appointments.get_owned_draft_for_update = AsyncMock(
        return_value=appointment
    )
    service.history.add = AsyncMock()

    result = await service.submit(user, now=now)

    assert result.status == SubmissionStatus.SUBMITTED
    assert appointment.status == AppointmentStatus.WAITING_ADMIN
    assert reservation.status == ReservationStatus.CONFIRMED
    assert reservation.reserved_until is None
    session.delete.assert_awaited_once_with(state)
    history = service.history.add.await_args.args[0]
    assert history.action == "submitted"
    assert history.new_value == {"status": "waiting_admin"}


async def test_expired_reservation_keeps_form_and_returns_to_time() -> None:
    now = datetime(2026, 7, 13, 8, tzinfo=UTC)
    user, slot, appointment, reservation, state = _objects(now)
    reservation.reserved_until = now - timedelta(seconds=1)
    restored = ConversationState(
        id=state.id,
        user_id=state.user_id,
        flow=state.flow,
        step="date_selection",
        payload=dict(state.payload),
        expires_at=state.expires_at,
    )
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[slot, slot])
    service = SubmissionService(session)
    service.states.get_active_for_flow = AsyncMock(return_value=state)
    service.states.upsert = AsyncMock(return_value=restored)
    service.reservations.get_blocking_for_appointment_for_update = AsyncMock(
        return_value=reservation
    )
    service.appointments.get_owned_draft_for_update = AsyncMock(
        return_value=appointment
    )

    result = await service.submit(user, now=now)

    assert result.status == SubmissionStatus.RESERVATION_EXPIRED
    assert appointment.status == AppointmentStatus.DRAFT
    assert appointment.customer_name == "Иван"
    assert appointment.customer_phone == "+79991234567"
    assert appointment.slot_id is None
    assert reservation.status == ReservationStatus.EXPIRED
    service.states.upsert.assert_awaited_once()
