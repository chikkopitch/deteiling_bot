"""Atomic customer submission of a fully populated draft."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import (
    AppointmentHistory,
    AvailableSlot,
    ConversationState,
    User,
)
from app.database.repositories import (
    AppointmentHistoryRepository,
    AppointmentRepository,
    ConversationStateRepository,
    ReservationRepository,
)
from app.services.user_entry import BOOKING_FLOW
from app.services.vehicle_selection import VehicleSelectionError


class SubmissionStatus(StrEnum):
    SUBMITTED = "submitted"
    RESERVATION_EXPIRED = "reservation_expired"


@dataclass(slots=True, frozen=True)
class SubmissionResult:
    status: SubmissionStatus
    appointment_id: UUID
    state: ConversationState | None


class SubmissionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.appointments = AppointmentRepository(session)
        self.reservations = ReservationRepository(session)
        self.states = ConversationStateRepository(session)
        self.history = AppointmentHistoryRepository(session)

    async def submit(
        self, user: User, *, now: datetime | None = None
    ) -> SubmissionResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        state = await self.states.get_active_for_flow(user.id, BOOKING_FLOW, current)
        if state is None or state.step != "review":
            raise VehicleSelectionError(
                "Итоговый экран устарел. Продолжите через /start."
            )
        appointment_id = self._payload_uuid(state, "appointment_id")
        reservation = await self.reservations.get_blocking_for_appointment_for_update(
            appointment_id
        )
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user.id
        )
        if appointment is None:
            raise VehicleSelectionError("Черновик уже отправлен или закрыт.")
        if reservation is None or appointment.slot_id is None:
            return await self._return_to_time(state, appointment, None, current)
        slot = await self.session.get(
            AvailableSlot, reservation.slot_id, with_for_update=True
        )
        if slot is None:
            return await self._return_to_time(state, appointment, reservation, current)
        if (
            reservation.status != ReservationStatus.ACTIVE
            or reservation.reserved_until is None
            or reservation.reserved_until <= current
        ):
            return await self._return_to_time(state, appointment, reservation, current)
        blocking = await self.reservations.get_blocking_for_slot_for_update(slot.id)
        if blocking is None or blocking.id != reservation.id:
            raise VehicleSelectionError("Слот занят другой заявкой.")
        if appointment.slot_id != slot.id or appointment.scheduled_at != slot.starts_at:
            raise VehicleSelectionError("Связь заявки со слотом повреждена.")
        if slot.blocked_reason is not None or slot.starts_at <= current:
            return await self._return_to_time(state, appointment, reservation, current)
        if not all(
            (
                appointment.service_id,
                appointment.vehicle_class_id,
                appointment.customer_name,
                appointment.customer_phone,
                appointment.scheduled_at,
            )
        ):
            raise VehicleSelectionError("Заполнены не все обязательные данные заявки.")

        reservation.status = ReservationStatus.CONFIRMED
        reservation.reserved_until = None
        slot.is_available = False
        appointment.status = AppointmentStatus.WAITING_ADMIN
        await self.history.add(
            AppointmentHistory(
                appointment_id=appointment.id,
                action="submitted",
                old_value={"status": AppointmentStatus.DRAFT.value},
                new_value={"status": AppointmentStatus.WAITING_ADMIN.value},
                changed_by_user_id=user.id,
            )
        )
        await self.session.delete(state)
        await self.session.flush()
        return SubmissionResult(SubmissionStatus.SUBMITTED, appointment.id, None)

    async def _return_to_time(
        self,
        state: ConversationState,
        appointment,
        reservation,
        current: datetime,
    ) -> SubmissionResult:
        if reservation is not None and reservation.status == ReservationStatus.ACTIVE:
            reservation.status = ReservationStatus.EXPIRED
        if appointment.slot_id is not None:
            slot = await self.session.get(
                AvailableSlot, appointment.slot_id, with_for_update=True
            )
            if slot is not None and slot.blocked_reason is None:
                slot.is_available = slot.starts_at > current
        appointment.slot_id = None
        appointment.scheduled_at = None
        payload = dict(state.payload)
        for key in ("slot_id", "scheduled_at", "reserved_until", "selected_date"):
            payload.pop(key, None)
        restored = await self.states.upsert(
            user_id=state.user_id,
            flow=state.flow,
            step="date_selection",
            payload=payload,
            expires_at=current + timedelta(days=30),
        )
        await self.session.flush()
        return SubmissionResult(
            SubmissionStatus.RESERVATION_EXPIRED, appointment.id, restored
        )

    @staticmethod
    def _payload_uuid(state: ConversationState, key: str) -> UUID:
        try:
            return UUID(str(state.payload.get(key)))
        except (TypeError, ValueError) as error:
            raise VehicleSelectionError("Сохранённые данные повреждены.") from error
