"""User entry, draft recovery, and safe scenario cancellation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import (
    Appointment,
    AppointmentSlotReservation,
    AvailableSlot,
    ConversationState,
    User,
)
from app.database.repositories import (
    AppointmentRepository,
    ContentSettingRepository,
    ConversationStateRepository,
)

DEFAULT_WELCOME_TEXT = (
    "Добро пожаловать в детейлинг-студию! Выберите нужный раздел в главном меню."
)
BOOKING_FLOW = "booking"
BOOKING_INITIAL_STEP = "vehicle_input"


@dataclass(slots=True, frozen=True)
class EntryContext:
    welcome_text: str
    draft: Appointment | None
    state: ConversationState | None


class UserEntryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.appointments = AppointmentRepository(session)
        self.states = ConversationStateRepository(session)
        self.content = ContentSettingRepository(session)

    async def load_context(self, user: User) -> EntryContext:
        now = datetime.now(UTC)
        welcome = await self.content.get_value("welcome_text", DEFAULT_WELCOME_TEXT)
        draft = await self.appointments.get_draft_for_user(user.id)
        state = await self.states.get_active_for_flow(user.id, BOOKING_FLOW, now)
        if draft is None and state is not None:
            await self.session.delete(state)
            state = None
        return EntryContext(welcome_text=welcome, draft=draft, state=state)

    async def begin_booking(self, user: User) -> tuple[Appointment, ConversationState]:
        # Serialize draft creation for one customer.
        await self.session.get(User, user.id, with_for_update=True)
        existing = await self.appointments.get_draft_for_user(user.id)
        if existing is not None:
            state = await self.states.get_active_for_flow(
                user.id, BOOKING_FLOW, datetime.now(UTC)
            )
            if state is None:
                state = await self.states.upsert(
                    user_id=user.id,
                    flow=BOOKING_FLOW,
                    step=BOOKING_INITIAL_STEP,
                    payload={"appointment_id": str(existing.id)},
                    expires_at=datetime.now(UTC) + timedelta(days=30),
                )
            return existing, state

        appointment = Appointment(user_id=user.id, status=AppointmentStatus.DRAFT)
        await self.appointments.add(appointment)
        state = await self.states.upsert(
            user_id=user.id,
            flow=BOOKING_FLOW,
            step=BOOKING_INITIAL_STEP,
            payload={"appointment_id": str(appointment.id)},
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        return appointment, state

    async def resume_booking(
        self, user: User, appointment_id: UUID
    ) -> tuple[Appointment, ConversationState] | None:
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user.id
        )
        if appointment is None:
            return None
        state = await self.states.get_active_for_flow(
            user.id, BOOKING_FLOW, datetime.now(UTC)
        )
        if state is None:
            state = await self.states.upsert(
                user_id=user.id,
                flow=BOOKING_FLOW,
                step=BOOKING_INITIAL_STEP,
                payload={"appointment_id": str(appointment.id)},
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        return appointment, state

    async def restart_booking(
        self, user: User, previous_appointment_id: UUID
    ) -> tuple[Appointment, ConversationState]:
        await self.close_draft(user.id, previous_appointment_id, "restart_draft")
        return await self.begin_booking(user)

    async def close_draft(
        self, user_id: UUID, appointment_id: UUID, reason: str
    ) -> bool:
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user_id
        )
        if appointment is None:
            return False

        appointment.status = AppointmentStatus.CANCELLED_BY_USER
        appointment.cancellation_reason = reason
        appointment.cancelled_at = datetime.now(UTC)

        reservations_result = await self.session.execute(
            select(AppointmentSlotReservation)
            .where(
                AppointmentSlotReservation.appointment_id == appointment.id,
                AppointmentSlotReservation.status == ReservationStatus.ACTIVE,
            )
            .with_for_update()
        )
        reservations = list(reservations_result.scalars())
        for reservation in reservations:
            reservation.status = ReservationStatus.CANCELLED
            slot = await self.session.get(
                AvailableSlot, reservation.slot_id, with_for_update=True
            )
            if slot is not None and slot.blocked_reason is None:
                slot.is_available = True
        appointment.slot_id = None
        appointment.scheduled_at = None

        state = await self.states.get_for_flow(user_id, BOOKING_FLOW)
        if state is not None:
            await self.session.delete(state)
        await self.session.flush()
        return True

    async def cancel_current(self, user: User) -> bool:
        state = await self.states.get_latest_active(user.id, datetime.now(UTC))
        if state is None:
            return False

        if state.flow == BOOKING_FLOW:
            raw_appointment_id = state.payload.get("appointment_id")
            if raw_appointment_id:
                try:
                    appointment_id = UUID(str(raw_appointment_id))
                except ValueError:
                    appointment_id = None
                if appointment_id is not None:
                    await self.close_draft(
                        user.id, appointment_id, "scenario_cancelled"
                    )

        persistent_state = await self.session.get(ConversationState, state.id)
        if persistent_state is not None:
            await self.session.delete(persistent_state)
        await self.session.flush()
        return True

    async def cancel_flow(self, user: User, flow: str) -> bool:
        state = await self.states.get_for_flow(user.id, flow)
        if state is None:
            return False
        if flow == BOOKING_FLOW:
            raw_appointment_id = state.payload.get("appointment_id")
            try:
                appointment_id = UUID(str(raw_appointment_id))
            except (ValueError, TypeError):
                appointment_id = None
            if appointment_id is not None:
                await self.close_draft(user.id, appointment_id, "scenario_cancelled")
        persistent_state = await self.session.get(ConversationState, state.id)
        if persistent_state is not None:
            await self.session.delete(persistent_state)
        await self.session.flush()
        return True
