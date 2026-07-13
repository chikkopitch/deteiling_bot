from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.database.enums import AppointmentStatus
from app.database.models import (
    Appointment,
    ConversationState,
    Service,
    ServicePrice,
    User,
    VehicleClass,
)
from app.services.service_selection import CONSULTATION_COMMENT, ServiceSelectionService
from app.services.user_entry import BOOKING_FLOW

pytestmark = pytest.mark.asyncio


def _user() -> User:
    return User(id=uuid4(), telegram_id=707070)


def _state(user: User, class_id=None) -> ConversationState:
    return ConversationState(
        id=uuid4(),
        user_id=user.id,
        flow=BOOKING_FLOW,
        step="service_selection",
        payload={
            "appointment_id": str(uuid4()),
            **({"vehicle_class_id": str(class_id)} if class_id else {}),
        },
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


async def test_booking_price_range_uses_class_specific_override() -> None:
    user = _user()
    vehicle_class = VehicleClass(
        id=uuid4(),
        name="кроссовер",
        price_coefficient=Decimal("1.5000"),
        is_active=True,
    )
    service_model = Service(
        id=uuid4(),
        name="Полировка",
        base_price=Decimal("1000.00"),
        duration_minutes=120,
        is_active=True,
    )
    override = ServicePrice(
        id=uuid4(),
        service_id=service_model.id,
        vehicle_class_id=vehicle_class.id,
        price=Decimal("1800.00"),
        min_price=Decimal("1700.00"),
        max_price=Decimal("1900.00"),
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=vehicle_class)
    service = ServiceSelectionService(session)
    service.states.get_active_for_flow = AsyncMock(
        return_value=_state(user, vehicle_class.id)
    )
    service.services.list_page = AsyncMock(return_value=([service_model], 1))
    service.services.get_price = AsyncMock(return_value=override)
    service.classes.list_active = AsyncMock(return_value=[vehicle_class])

    page = await service.page(user, BOOKING_FLOW)

    assert page.cards[0].price_from == Decimal("1700.00")
    assert page.cards[0].price_to == Decimal("1900.00")


async def test_consultation_preserves_vehicle_and_appends_comment() -> None:
    user = _user()
    class_id = uuid4()
    brand_id = uuid4()
    model_id = uuid4()
    vehicle_class = VehicleClass(
        id=class_id,
        name="седан",
        price_coefficient=Decimal("1.0000"),
        is_active=True,
    )
    free_service = Service(
        id=uuid4(),
        name="Бесплатный осмотр",
        base_price=Decimal("0.00"),
        duration_minutes=30,
        is_free_inspection=True,
        is_active=True,
    )
    state = _state(user, class_id)
    appointment = Appointment(
        id=uuid4(),
        user_id=user.id,
        vehicle_brand_id=brand_id,
        vehicle_model_id=model_id,
        vehicle_class_id=class_id,
        vehicle_comment="Исходный комментарий",
        status=AppointmentStatus.DRAFT,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=vehicle_class)
    service = ServiceSelectionService(session)
    service.services.get_active = AsyncMock(return_value=free_service)
    service.services.get_price = AsyncMock(return_value=None)
    service.classes.list_active = AsyncMock(return_value=[vehicle_class])
    service._state_and_appointment = AsyncMock(return_value=(state, appointment))
    service._save_state = AsyncMock(return_value=state)

    await service.select(user, BOOKING_FLOW, free_service.id, consultation=True)

    assert appointment.vehicle_brand_id == brand_id
    assert appointment.vehicle_model_id == model_id
    assert appointment.service_id == free_service.id
    assert (
        appointment.vehicle_comment == f"Исходный комментарий\n{CONSULTATION_COMMENT}"
    )
    _, step, payload = service._save_state.await_args.args
    assert step == "date_selection"
    assert payload["consultation"] is True
