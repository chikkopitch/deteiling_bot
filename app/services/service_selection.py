"""Service catalog presentation and class-aware price selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Appointment,
    ConversationState,
    Service,
    User,
    VehicleClass,
)
from app.database.repositories import (
    AppointmentRepository,
    ConversationStateRepository,
    ServiceRepository,
    VehicleClassRepository,
)
from app.services.user_entry import BOOKING_FLOW
from app.services.vehicle_selection import VehicleSelectionError

SERVICE_PAGE_SIZE = 5
STATE_TTL = timedelta(days=30)
CONSULTATION_COMMENT = "Нужна консультация по выбору услуги."


@dataclass(slots=True, frozen=True)
class ServiceCard:
    service: Service
    price_from: Decimal
    price_to: Decimal


@dataclass(slots=True, frozen=True)
class ServicePage:
    cards: list[ServiceCard]
    page: int
    pages: int


class ServiceSelectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.services = ServiceRepository(session)
        self.states = ConversationStateRepository(session)
        self.appointments = AppointmentRepository(session)
        self.classes = VehicleClassRepository(session)

    async def page(self, user: User, flow: str, page: int = 0) -> ServicePage:
        expected_step = (
            "service_selection" if flow == BOOKING_FLOW else "price_services"
        )
        state = await self._require_state(user.id, flow, {expected_step})
        page = max(page, 0)
        items, total = await self.services.list_page(
            offset=page * SERVICE_PAGE_SIZE, limit=SERVICE_PAGE_SIZE
        )
        pages = max(1, (total + SERVICE_PAGE_SIZE - 1) // SERVICE_PAGE_SIZE)
        if page >= pages:
            page = pages - 1
            items, _ = await self.services.list_page(
                offset=page * SERVICE_PAGE_SIZE, limit=SERVICE_PAGE_SIZE
            )

        if flow == BOOKING_FLOW:
            cards = [await self._booking_card(item) for item in items]
        else:
            vehicle_class_id = self._payload_uuid(state, "vehicle_class_id")
            vehicle_class = await self.session.get(VehicleClass, vehicle_class_id)
            if vehicle_class is None or not vehicle_class.is_active:
                raise VehicleSelectionError("Класс автомобиля больше недоступен.")
            cards = [await self._card(item, vehicle_class) for item in items]
        return ServicePage(cards=cards, page=page, pages=pages)

    async def select(
        self,
        user: User,
        flow: str,
        service_id: UUID,
        *,
        consultation: bool = False,
    ) -> ConversationState:
        service = await self.services.get_active(service_id)
        if service is None:
            raise VehicleSelectionError("Услуга больше недоступна. Обновите список.")
        state, appointment = await self._state_and_appointment(user, flow)
        if flow == BOOKING_FLOW:
            card = await self._booking_card(service)
        else:
            vehicle_class_id = self._payload_uuid(state, "vehicle_class_id")
            vehicle_class = await self.session.get(VehicleClass, vehicle_class_id)
            if vehicle_class is None or not vehicle_class.is_active:
                raise VehicleSelectionError("Класс автомобиля больше недоступен.")
            card = await self._card(service, vehicle_class)
        payload = dict(state.payload)
        payload.update(
            service_id=str(service.id),
            service_name=service.name,
            estimated_price_from=str(card.price_from),
            estimated_price_to=str(card.price_to),
            consultation=consultation,
        )
        next_step = "date_selection" if flow == BOOKING_FLOW else "price_factors"
        if flow != BOOKING_FLOW:
            payload["factor_index"] = 0
            payload["factor_selections"] = {}

        if appointment is not None:
            appointment.service_id = service.id
            appointment.estimated_price_from = card.price_from
            appointment.estimated_price_to = card.price_to
            if consultation:
                existing = (appointment.vehicle_comment or "").strip()
                if CONSULTATION_COMMENT not in existing:
                    appointment.vehicle_comment = (
                        f"{existing}\n{CONSULTATION_COMMENT}".strip()
                    )
        return await self._save_state(state, next_step, payload)

    async def select_free_inspection(
        self, user: User, flow: str, *, consultation: bool
    ) -> ConversationState:
        service = await self.services.get_free_inspection()
        if service is None:
            raise VehicleSelectionError(
                "Бесплатный осмотр временно недоступен. Обратитесь к менеджеру."
            )
        return await self.select(user, flow, service.id, consultation=consultation)

    async def _card(self, service: Service, vehicle_class: VehicleClass) -> ServiceCard:
        override = await self.services.get_price(service.id, vehicle_class.id)
        if override is not None:
            price_from = (
                override.min_price if override.min_price is not None else override.price
            )
            price_to = (
                override.max_price if override.max_price is not None else override.price
            )
        else:
            calculated = service.base_price * vehicle_class.price_coefficient
            price_from = price_to = calculated
        quant = Decimal("0.01")
        return ServiceCard(
            service=service,
            price_from=price_from.quantize(quant, rounding=ROUND_HALF_UP),
            price_to=price_to.quantize(quant, rounding=ROUND_HALF_UP),
        )

    async def _booking_card(self, service: Service) -> ServiceCard:
        """Return the visible booking price range without asking for a car class."""
        classes = await self.classes.list_active()
        if not classes:
            raise VehicleSelectionError("Администратор ещё не настроил классы автомобилей для расчёта цен.")
        cards = [await self._card(service, vehicle_class) for vehicle_class in classes]
        return ServiceCard(
            service=service,
            price_from=min(card.price_from for card in cards),
            price_to=max(card.price_to for card in cards),
        )

    async def _require_state(
        self, user_id: UUID, flow: str, allowed_steps: set[str] | None = None
    ) -> ConversationState:
        state = await self.states.get_active_for_flow(user_id, flow, datetime.now(UTC))
        if state is None:
            raise VehicleSelectionError("Сценарий истёк. Начните заново.")
        if allowed_steps is not None and state.step not in allowed_steps:
            raise VehicleSelectionError(
                "Эта кнопка устарела. Продолжите с текущего шага."
            )
        return state

    async def _state_and_appointment(
        self, user: User, flow: str
    ) -> tuple[ConversationState, Appointment | None]:
        expected_step = (
            "service_selection" if flow == BOOKING_FLOW else "price_services"
        )
        state = await self._require_state(user.id, flow, {expected_step})
        if flow != BOOKING_FLOW:
            return state, None
        appointment_id = self._payload_uuid(state, "appointment_id")
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

    @staticmethod
    def _payload_uuid(state: ConversationState, key: str) -> UUID:
        try:
            return UUID(str(state.payload.get(key)))
        except (TypeError, ValueError) as error:
            raise VehicleSelectionError("Сохранённые данные повреждены.") from error
