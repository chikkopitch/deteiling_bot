"""Contact collection and normalization for a booking draft."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Appointment, ConversationState, User
from app.database.repositories import AppointmentRepository, ConversationStateRepository
from app.services.user_entry import BOOKING_FLOW
from app.services.vehicle_selection import VehicleSelectionError, clean_user_text

STATE_TTL = timedelta(days=30)


def normalize_person_name(value: str) -> str:
    return clean_user_text(value, min_length=1, max_length=120)


def normalize_russian_phone(value: str) -> str:
    compact = re.sub(r"[\s()\-]", "", value.strip())
    if compact.startswith("+"):
        compact = compact[1:]
    if len(compact) != 11 or not all("0" <= char <= "9" for char in compact):
        raise VehicleSelectionError(
            "Введите российский номер из 11 цифр, например +79991234567."
        )
    if compact.startswith("8"):
        compact = "7" + compact[1:]
    if not compact.startswith("7"):
        raise VehicleSelectionError("Российский номер должен начинаться с +7, 7 или 8.")
    return "+" + compact


class ContactService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.appointments = AppointmentRepository(session)
        self.states = ConversationStateRepository(session)

    async def suggested_name(self, user: User) -> str | None:
        raw = " ".join(part for part in (user.first_name, user.last_name) if part)
        if not raw.strip():
            return None
        try:
            return normalize_person_name(raw)
        except VehicleSelectionError:
            return None

    async def save_name(self, user: User, value: str) -> ConversationState:
        normalized = normalize_person_name(value)
        state, appointment = await self._state_and_appointment(
            user, {"contact_name", "contact_name_input"}
        )
        appointment.customer_name = normalized
        payload = dict(state.payload)
        payload["customer_name"] = normalized
        return await self._save_state(state, "contact_phone", payload)

    async def save_phone(self, user: User, value: str) -> ConversationState:
        normalized = normalize_russian_phone(value)
        state, appointment = await self._state_and_appointment(
            user, {"contact_phone", "contact_phone_input"}
        )
        appointment.customer_phone = normalized
        user.phone = normalized
        payload = dict(state.payload)
        payload["customer_phone"] = normalized
        return await self._save_state(state, "review", payload)

    async def set_step(self, user: User, step: str) -> ConversationState:
        state, _ = await self._state_and_appointment(
            user,
            {
                "contact_name",
                "contact_name_input",
                "contact_phone",
                "contact_phone_input",
                "review",
            },
        )
        return await self._save_state(state, step, dict(state.payload))

    async def _state_and_appointment(
        self, user: User, allowed_steps: set[str]
    ) -> tuple[ConversationState, Appointment]:
        state = await self.states.get_active_for_flow(
            user.id, BOOKING_FLOW, datetime.now(UTC)
        )
        if state is None:
            raise VehicleSelectionError("Сценарий истёк. Начните заново.")
        if state.step not in allowed_steps:
            raise VehicleSelectionError(
                "Этот экран устарел. Продолжите с текущего шага."
            )
        try:
            appointment_id = UUID(str(state.payload.get("appointment_id")))
        except (TypeError, ValueError) as error:
            raise VehicleSelectionError("Сохранённые данные повреждены.") from error
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user.id
        )
        if appointment is None:
            raise VehicleSelectionError("Черновик уже закрыт.")
        return state, appointment

    async def _save_state(
        self, state: ConversationState, step: str, payload: dict
    ) -> ConversationState:
        await self.session.flush()
        return await self.states.upsert(
            user_id=state.user_id,
            flow=state.flow,
            step=step,
            payload=payload,
            expires_at=datetime.now(UTC) + STATE_TTL,
        )
