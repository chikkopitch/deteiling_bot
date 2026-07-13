"""Persistent vehicle selection shared by booking and price calculation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Appointment,
    ConversationState,
    User,
    VehicleBrand,
    VehicleClass,
    VehicleModel,
)
from app.database.repositories import (
    AppointmentRepository,
    ConversationStateRepository,
    VehicleBrandRepository,
    VehicleClassRepository,
    VehicleModelRepository,
)
from app.services.user_entry import BOOKING_FLOW

PRICE_FLOW = "price_calculation"
FLOW_CODES = {"b": BOOKING_FLOW, "p": PRICE_FLOW}
FLOW_NAMES_TO_CODES = {value: key for key, value in FLOW_CODES.items()}
PAGE_SIZE = 8
STATE_TTL = timedelta(days=30)


class VehicleSelectionError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class Page:
    items: list[VehicleBrand] | list[VehicleModel]
    page: int
    pages: int
    search: str | None


def clean_user_text(value: str, *, min_length: int = 1, max_length: int = 120) -> str:
    cleaned = "".join(
        " " if unicodedata.category(char)[0] == "C" else char for char in value.strip()
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not min_length <= len(cleaned) <= max_length:
        raise VehicleSelectionError(
            f"Введите от {min_length} до {max_length} символов."
        )
    return cleaned


def validate_vehicle_year(value: str, *, now: datetime | None = None) -> int:
    normalized = value.strip()
    if not normalized.isdecimal() or len(normalized) != 4:
        raise VehicleSelectionError("Введите год четырьмя цифрами, например 2020.")
    year = int(normalized)
    current_year = (now or datetime.now(UTC)).year
    if year < 1900 or year > current_year + 1:
        raise VehicleSelectionError(f"Допустим год от 1900 до {current_year + 1}.")
    return year


class VehicleSelectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.states = ConversationStateRepository(session)
        self.appointments = AppointmentRepository(session)
        self.brands = VehicleBrandRepository(session)
        self.models = VehicleModelRepository(session)
        self.classes = VehicleClassRepository(session)

    async def get_state(self, user_id: UUID, flow: str) -> ConversationState | None:
        return await self.states.get_active_for_flow(user_id, flow, datetime.now(UTC))

    async def start_price_calculation(self, user: User) -> ConversationState:
        existing = await self.get_state(user.id, PRICE_FLOW)
        if existing is not None:
            return existing
        return await self.states.upsert(
            user_id=user.id,
            flow=PRICE_FLOW,
            step="vehicle_brand",
            payload={},
            expires_at=datetime.now(UTC) + STATE_TTL,
        )

    async def save_vehicle_description(
        self, user: User, flow: str, raw_value: str
    ) -> ConversationState:
        """Save a customer's vehicle entered as one free-form value."""
        value = clean_user_text(raw_value, min_length=3)
        state, appointment = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload.update(
            vehicle_brand_id=None,
            vehicle_brand_name=None,
            vehicle_model_id=None,
            vehicle_model_name=None,
            vehicle_class_id=None,
            vehicle_class_name=None,
            custom_vehicle_brand=value,
            custom_vehicle_model=None,
            vehicle_year=None,
        )
        if appointment is not None:
            appointment.vehicle_brand_id = None
            appointment.vehicle_model_id = None
            appointment.vehicle_class_id = None
            appointment.custom_vehicle_brand = value
            appointment.custom_vehicle_model = None
            appointment.vehicle_year = None
        return await self._save_state(state, "service_selection", payload)

    async def brands_page(self, user_id: UUID, flow: str, page: int = 0) -> Page:
        state = await self._require_state(user_id, flow)
        search = state.payload.get("brand_search")
        return await self._brand_page(page, search)

    async def _brand_page(self, page: int, search: str | None) -> Page:
        page = max(page, 0)
        items, total = await self.brands.list_page(
            offset=page * PAGE_SIZE, limit=PAGE_SIZE, search=search
        )
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if page >= pages:
            page = pages - 1
            items, _ = await self.brands.list_page(
                offset=page * PAGE_SIZE, limit=PAGE_SIZE, search=search
            )
        return Page(items=items, page=page, pages=pages, search=search)

    async def models_page(self, user_id: UUID, flow: str, page: int = 0) -> Page:
        state = await self._require_state(user_id, flow)
        brand_id = self._payload_uuid(state, "vehicle_brand_id")
        search = state.payload.get("model_search")
        page = max(page, 0)
        items, total = await self.models.list_page_for_brand(
            brand_id,
            offset=page * PAGE_SIZE,
            limit=PAGE_SIZE,
            search=search,
        )
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if page >= pages:
            page = pages - 1
            items, _ = await self.models.list_page_for_brand(
                brand_id,
                offset=page * PAGE_SIZE,
                limit=PAGE_SIZE,
                search=search,
            )
        return Page(items=items, page=page, pages=pages, search=search)

    async def list_classes(self) -> list[VehicleClass]:
        return await self.classes.list_active()

    async def select_brand(
        self, user: User, flow: str, brand_id: UUID
    ) -> ConversationState:
        brand = await self.brands.get_active(brand_id)
        if brand is None:
            raise VehicleSelectionError("Марка больше недоступна. Обновите список.")
        state, appointment = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload.update(
            vehicle_brand_id=str(brand.id),
            vehicle_brand_name=brand.name,
            vehicle_model_id=None,
            vehicle_class_id=None,
            custom_vehicle_brand=None,
            custom_vehicle_model=None,
            model_search=None,
        )
        if appointment is not None:
            appointment.vehicle_brand_id = brand.id
            appointment.vehicle_model_id = None
            appointment.vehicle_class_id = None
            appointment.custom_vehicle_brand = None
            appointment.custom_vehicle_model = None
        return await self._save_state(state, "vehicle_model", payload)

    async def select_model(
        self, user: User, flow: str, model_id: UUID
    ) -> ConversationState:
        state, appointment = await self._state_and_appointment(user, flow)
        brand_id = self._payload_uuid(state, "vehicle_brand_id")
        model = await self.models.get_active_for_brand(model_id, brand_id)
        if model is None:
            raise VehicleSelectionError("Модель больше недоступна. Обновите список.")
        payload = dict(state.payload)
        payload.update(
            vehicle_model_id=str(model.id),
            vehicle_model_name=model.name,
            vehicle_class_id=str(model.vehicle_class_id),
            custom_vehicle_model=None,
            year_return_step="vehicle_model",
        )
        if appointment is not None:
            appointment.vehicle_model_id = model.id
            appointment.vehicle_class_id = model.vehicle_class_id
            appointment.custom_vehicle_model = None
        return await self._save_state(state, "vehicle_year", payload)

    async def request_custom_brand(self, user: User, flow: str) -> ConversationState:
        state, _ = await self._state_and_appointment(user, flow)
        return await self._save_state(
            state, "custom_vehicle_brand", dict(state.payload)
        )

    async def save_custom_brand(
        self, user: User, flow: str, raw_value: str
    ) -> ConversationState:
        value = clean_user_text(raw_value, min_length=2)
        state, appointment = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload.update(
            custom_vehicle_brand=value,
            vehicle_brand_id=None,
            vehicle_model_id=None,
            vehicle_class_id=None,
            custom_vehicle_model=None,
        )
        if appointment is not None:
            appointment.vehicle_brand_id = None
            appointment.vehicle_model_id = None
            appointment.vehicle_class_id = None
            appointment.custom_vehicle_brand = value
            appointment.custom_vehicle_model = None
        return await self._save_state(state, "custom_vehicle_model", payload)

    async def request_custom_model(self, user: User, flow: str) -> ConversationState:
        state, _ = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload["class_return_step"] = "custom_vehicle_model"
        return await self._save_state(state, "custom_vehicle_model", payload)

    async def save_custom_model(
        self, user: User, flow: str, raw_value: str
    ) -> ConversationState:
        value = clean_user_text(raw_value, min_length=1)
        state, appointment = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload.update(
            custom_vehicle_model=value,
            vehicle_model_id=None,
            vehicle_class_id=None,
            class_return_step="custom_vehicle_model",
        )
        if appointment is not None:
            appointment.vehicle_model_id = None
            appointment.vehicle_class_id = None
            appointment.custom_vehicle_model = value
        return await self._save_state(state, "vehicle_class", payload)

    async def select_class(
        self, user: User, flow: str, vehicle_class_id: UUID
    ) -> ConversationState:
        vehicle_class = await self.session.get(VehicleClass, vehicle_class_id)
        if vehicle_class is None or not vehicle_class.is_active:
            raise VehicleSelectionError("Класс автомобиля больше недоступен.")
        state, appointment = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload.update(
            vehicle_class_id=str(vehicle_class.id),
            vehicle_class_name=vehicle_class.name,
            year_return_step="vehicle_class",
        )
        if appointment is not None:
            appointment.vehicle_class_id = vehicle_class.id
        return await self._save_state(state, "vehicle_year", payload)

    async def save_year(
        self, user: User, flow: str, raw_value: str | None
    ) -> ConversationState:
        year = None if raw_value is None else validate_vehicle_year(raw_value)
        state, appointment = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload["vehicle_year"] = year
        if appointment is not None:
            appointment.vehicle_year = year
        next_step = "service_selection" if flow == BOOKING_FLOW else "price_services"
        return await self._save_state(state, next_step, payload)

    async def set_step(
        self, user: User, flow: str, step: str, **payload_updates: object
    ) -> ConversationState:
        state, _ = await self._state_and_appointment(user, flow)
        payload = dict(state.payload)
        payload.update(payload_updates)
        return await self._save_state(state, step, payload)

    async def _require_state(self, user_id: UUID, flow: str) -> ConversationState:
        state = await self.get_state(user_id, flow)
        if state is None:
            raise VehicleSelectionError("Сценарий истёк. Начните заново из меню.")
        return state

    async def _state_and_appointment(
        self, user: User, flow: str
    ) -> tuple[ConversationState, Appointment | None]:
        state = await self._require_state(user.id, flow)
        if flow != BOOKING_FLOW:
            return state, None
        appointment_id = self._payload_uuid(state, "appointment_id")
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user.id
        )
        if appointment is None:
            raise VehicleSelectionError("Черновик уже закрыт. Начните новую запись.")
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

    @staticmethod
    def _payload_uuid(state: ConversationState, key: str) -> UUID:
        raw = state.payload.get(key)
        try:
            return UUID(str(raw))
        except (ValueError, TypeError) as error:
            raise VehicleSelectionError(
                "Сохранённые данные повреждены. Начните заново."
            ) from error
