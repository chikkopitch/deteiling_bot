from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.bot.handlers.schedule import render_schedule_step
from app.bot.keyboards.schedule import calendar_keyboard
from app.core.config import Settings
from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import (
    Appointment,
    AppointmentSlotReservation,
    AvailableSlot,
    ConversationState,
    User,
)
from app.scheduler.reservations import expire_reservations_once
from app.services.schedule import CalendarMonth, ScheduleService, SlotUnavailableError

pytestmark = pytest.mark.asyncio


def _user() -> User:
    return User(id=uuid4(), telegram_id=909090)


def _state(
    user: User, appointment_id, step: str = "date_selection"
) -> ConversationState:
    return ConversationState(
        id=uuid4(),
        user_id=user.id,
        flow="booking",
        step=step,
        payload={"appointment_id": str(appointment_id)},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def _service(session) -> ScheduleService:
    return ScheduleService(
        session,
        timezone=ZoneInfo("Europe/Moscow"),
        booking_days_ahead=30,
        reservation_minutes=15,
    )


async def test_calendar_only_enables_available_dates() -> None:
    available = date(2026, 7, 20)
    keyboard = calendar_keyboard(
        CalendarMonth(
            year=2026,
            month=7,
            available_dates=frozenset({available}),
            can_previous=False,
            can_next=True,
        )
    )
    selectable = [
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == f"sch:date:{available.isoformat()}"
    ]
    assert len(selectable) == 1


async def test_past_date_is_rejected() -> None:
    user = _user()
    service = _service(AsyncMock())

    with pytest.raises(SlotUnavailableError, match="прошедшую"):
        await service.times_for_date(
            user,
            date(2026, 7, 11),
            now=datetime(2026, 7, 12, 8, tzinfo=UTC),
        )


async def test_blocked_slot_is_rejected() -> None:
    user = _user()
    appointment = Appointment(
        id=uuid4(), user_id=user.id, status=AppointmentStatus.DRAFT
    )
    state = _state(user, appointment.id)
    slot = AvailableSlot(
        id=uuid4(),
        starts_at=datetime(2026, 7, 15, 9, tzinfo=UTC),
        ends_at=datetime(2026, 7, 15, 10, tzinfo=UTC),
        is_available=False,
        blocked_reason="Технические работы",
    )
    service = _service(AsyncMock())
    service._require_state = AsyncMock(return_value=state)
    service.reservations.get_blocking_for_appointment_for_update = AsyncMock(
        return_value=None
    )
    service.appointments.get_owned_draft_for_update = AsyncMock(
        return_value=appointment
    )
    service.slots.get_for_update = AsyncMock(return_value=slot)
    service.reservations.get_blocking_for_slot_for_update = AsyncMock(return_value=None)

    with pytest.raises(SlotUnavailableError, match="заблокирован"):
        await service.reserve(user, slot.id, now=datetime(2026, 7, 12, 8, tzinfo=UTC))


async def test_expired_reservation_releases_slot_and_draft() -> None:
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)
    user = _user()
    slot = AvailableSlot(
        id=uuid4(),
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=1),
        is_available=False,
    )
    appointment = Appointment(
        id=uuid4(),
        user_id=user.id,
        slot_id=slot.id,
        scheduled_at=slot.starts_at,
        status=AppointmentStatus.DRAFT,
    )
    reservation = AppointmentSlotReservation(
        id=uuid4(),
        appointment_id=appointment.id,
        slot_id=slot.id,
        reserved_until=now - timedelta(minutes=1),
        status=ReservationStatus.ACTIVE,
    )
    state = _state(user, appointment.id, step="contact_name")
    state.payload.update(
        slot_id=str(slot.id),
        scheduled_at=slot.starts_at.isoformat(),
        reserved_until=reservation.reserved_until.isoformat(),
    )
    result = Mock()
    result.scalars.return_value = [reservation]
    state_result = Mock()
    state_result.scalar_one_or_none.return_value = state
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[result, state_result])
    session.get = AsyncMock(side_effect=[appointment, slot])

    count = await expire_reservations_once(session, now=now)

    assert count == 1
    assert reservation.status == ReservationStatus.EXPIRED
    assert slot.is_available is True
    assert appointment.slot_id is None
    assert appointment.scheduled_at is None
    assert state.step == "date_selection"
    assert "slot_id" not in state.payload


async def test_reserved_time_is_restored_after_restart() -> None:
    user = _user()
    appointment_id = uuid4()
    starts_at = datetime(2026, 7, 20, 9, tzinfo=UTC)
    reserved_until = datetime(2026, 7, 12, 9, tzinfo=UTC)
    state = _state(user, appointment_id, step="contact_name")
    state.payload.update(
        scheduled_at=starts_at.isoformat(),
        reserved_until=reserved_until.isoformat(),
    )
    message = SimpleNamespace(answer=AsyncMock())
    settings = Settings(
        bot_token="123456789:abcdefghijklmnopqrstuvwxyzABCDE",
        database_url="postgresql+asyncpg://user:password@localhost/database",
        owner_telegram_id=1,
        _env_file=None,
    )

    await render_schedule_step(message, user, AsyncMock(), settings, state)

    args, _ = message.answer.await_args
    assert "временно зарезервировано" in args[0]
    assert "20.07.2026" in args[0]
