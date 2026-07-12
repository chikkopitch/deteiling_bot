"""Timezone-aware calendar, availability, and transactional slot reservation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database.enums import ReservationStatus
from app.database.models import (
    AppointmentSlotReservation,
    AvailableSlot,
    ConversationState,
    User,
)
from app.database.repositories import (
    AppointmentRepository,
    AvailableSlotRepository,
    ConversationStateRepository,
    ReservationRepository,
)
from app.services.user_entry import BOOKING_FLOW
from app.services.vehicle_selection import VehicleSelectionError

STATE_TTL = timedelta(days=30)


class SlotUnavailableError(VehicleSelectionError):
    pass


@dataclass(slots=True, frozen=True)
class CalendarMonth:
    year: int
    month: int
    available_dates: frozenset[date]
    can_previous: bool
    can_next: bool


@dataclass(slots=True, frozen=True)
class ReservationResult:
    reservation: AppointmentSlotReservation
    slot: AvailableSlot
    state: ConversationState


class ScheduleService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        timezone: ZoneInfo,
        booking_days_ahead: int,
        reservation_minutes: int,
    ) -> None:
        self.session = session
        self.timezone = timezone
        self.booking_days_ahead = booking_days_ahead
        self.reservation_minutes = reservation_minutes
        self.slots = AvailableSlotRepository(session)
        self.reservations = ReservationRepository(session)
        self.appointments = AppointmentRepository(session)
        self.states = ConversationStateRepository(session)

    async def calendar_month(
        self, user: User, year: int, month: int, *, now: datetime | None = None
    ) -> CalendarMonth:
        current = (now or datetime.now(UTC)).astimezone(self.timezone)
        today = current.date()
        maximum = today + timedelta(days=self.booking_days_ahead)
        requested = date(year, month, 1)
        first_allowed = today.replace(day=1)
        last_allowed = maximum.replace(day=1)
        if requested < first_allowed or requested > last_allowed:
            raise VehicleSelectionError("Этот месяц находится вне периода записи.")
        await self._require_state(user.id, "date_selection")

        next_month = self._next_month(requested)
        local_from = max(requested, today)
        local_to = min(next_month, maximum + timedelta(days=1))
        utc_from = datetime.combine(local_from, time.min, self.timezone).astimezone(UTC)
        utc_to = datetime.combine(local_to, time.min, self.timezone).astimezone(UTC)
        slots = await self.slots.list_available_between(
            utc_from, utc_to, current.astimezone(UTC)
        )
        dates = frozenset(
            slot.starts_at.astimezone(self.timezone).date() for slot in slots
        )
        return CalendarMonth(
            year=year,
            month=month,
            available_dates=dates,
            can_previous=requested > first_allowed,
            can_next=requested < last_allowed,
        )

    async def times_for_date(
        self, user: User, selected_date: date, *, now: datetime | None = None
    ) -> list[AvailableSlot]:
        current = (now or datetime.now(UTC)).astimezone(self.timezone)
        today = current.date()
        maximum = today + timedelta(days=self.booking_days_ahead)
        if selected_date < today:
            raise SlotUnavailableError("Нельзя выбрать прошедшую дату.")
        if selected_date > maximum:
            raise SlotUnavailableError("Дата находится за пределами периода записи.")
        await self._require_state(user.id, "date_selection")
        local_from = datetime.combine(selected_date, time.min, self.timezone)
        local_to = local_from + timedelta(days=1)
        return await self.slots.list_available_between(
            local_from.astimezone(UTC),
            local_to.astimezone(UTC),
            current.astimezone(UTC),
        )

    async def reserve(
        self, user: User, slot_id: UUID, *, now: datetime | None = None
    ) -> ReservationResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        state = await self._require_state(user.id, "date_selection")
        appointment_id = self._payload_uuid(state, "appointment_id")

        # Existing reservation is locked first; cleanup workers use the same order.
        existing = await self.reservations.get_blocking_for_appointment_for_update(
            appointment_id
        )
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user.id
        )
        if appointment is None:
            raise SlotUnavailableError("Черновик уже закрыт.")
        slot = await self.slots.get_for_update(slot_id)
        if slot is None:
            raise SlotUnavailableError("Слот не найден.")

        if existing is not None and existing.slot_id == slot.id:
            if (
                existing.status == ReservationStatus.ACTIVE
                and existing.reserved_until is not None
                and existing.reserved_until > current
            ):
                new_state = await self._save_reserved_state(state, slot, existing)
                return ReservationResult(existing, slot, new_state)
            if (
                existing.status == ReservationStatus.ACTIVE
                and existing.reserved_until is not None
                and existing.reserved_until <= current
            ):
                existing.status = ReservationStatus.EXPIRED
                slot.is_available = slot.blocked_reason is None
                existing = None

        blocking = await self.reservations.get_blocking_for_slot_for_update(slot.id)
        if blocking is not None and blocking.id != getattr(existing, "id", None):
            if (
                blocking.status == ReservationStatus.ACTIVE
                and blocking.reserved_until is not None
                and blocking.reserved_until <= current
            ):
                blocking.status = ReservationStatus.EXPIRED
                slot.is_available = slot.blocked_reason is None
            else:
                raise SlotUnavailableError("Это время уже занято.")

        local_today = current.astimezone(self.timezone).date()
        maximum = local_today + timedelta(days=self.booking_days_ahead)
        slot_local_date = slot.starts_at.astimezone(self.timezone).date()
        if slot.starts_at <= current or slot_local_date < local_today:
            raise SlotUnavailableError("Нельзя выбрать прошедшее время.")
        if slot_local_date > maximum:
            raise SlotUnavailableError("Слот находится за пределами периода записи.")
        if slot.blocked_reason is not None:
            raise SlotUnavailableError("Слот заблокирован администратором.")
        if not slot.is_available:
            raise SlotUnavailableError("Это время уже недоступно.")

        if existing is not None:
            if existing.status == ReservationStatus.CONFIRMED:
                raise SlotUnavailableError(
                    "Подтверждённую запись нельзя заменить этим действием."
                )
            existing.status = ReservationStatus.CANCELLED
            old_slot = await self.slots.get_for_update(existing.slot_id)
            if old_slot is not None and old_slot.blocked_reason is None:
                old_slot.is_available = True

        reserved_until = current + timedelta(minutes=self.reservation_minutes)
        reservation = AppointmentSlotReservation(
            appointment_id=appointment.id,
            slot_id=slot.id,
            reserved_until=reserved_until,
            status=ReservationStatus.ACTIVE,
        )
        try:
            async with self.session.begin_nested():
                await self.reservations.add(reservation)
        except IntegrityError as error:
            raise SlotUnavailableError("Это время уже занято.") from error
        slot.is_available = False
        appointment.slot_id = slot.id
        appointment.scheduled_at = slot.starts_at
        new_state = await self._save_reserved_state(state, slot, reservation)
        return ReservationResult(reservation, slot, new_state)

    async def _require_state(self, user_id: UUID, step: str) -> ConversationState:
        state = await self.states.get_active_for_flow(
            user_id, BOOKING_FLOW, datetime.now(UTC)
        )
        if state is None:
            raise VehicleSelectionError("Сценарий истёк. Начните заново.")
        if state.step != step:
            raise VehicleSelectionError(
                "Этот экран устарел. Продолжите с текущего шага."
            )
        return state

    async def _save_reserved_state(
        self,
        state: ConversationState,
        slot: AvailableSlot,
        reservation: AppointmentSlotReservation,
    ) -> ConversationState:
        payload = dict(state.payload)
        payload.update(
            slot_id=str(slot.id),
            scheduled_at=slot.starts_at.isoformat(),
            reserved_until=(
                reservation.reserved_until.isoformat()
                if reservation.reserved_until is not None
                else None
            ),
        )
        await self.session.flush()
        return await self.states.upsert(
            user_id=state.user_id,
            flow=state.flow,
            step="contact_name",
            payload=payload,
            expires_at=datetime.now(UTC) + STATE_TTL,
        )

    @staticmethod
    def _payload_uuid(state: ConversationState, key: str) -> UUID:
        try:
            return UUID(str(state.payload.get(key)))
        except (TypeError, ValueError) as error:
            raise VehicleSelectionError("Сохранённые данные повреждены.") from error

    @staticmethod
    def _next_month(value: date) -> date:
        return date(value.year + (value.month == 12), value.month % 12 + 1, 1)
