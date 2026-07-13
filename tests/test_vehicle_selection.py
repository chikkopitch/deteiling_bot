from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.bot.handlers.vehicle import handle_vehicle_callback, render_vehicle_step
from app.bot.keyboards import VehicleCallback
from app.bot.keyboards.vehicle import brands_keyboard
from app.database.enums import AppointmentStatus
from app.database.models import (
    Appointment,
    ConversationState,
    User,
    VehicleBrand,
    VehicleModel,
)
from app.services.user_entry import BOOKING_FLOW
from app.services.vehicle_selection import (
    VehicleSelectionError,
    VehicleSelectionService,
    Page,
    clean_user_text,
    validate_vehicle_year,
)

pytestmark = pytest.mark.asyncio


def _user() -> User:
    return User(id=uuid4(), telegram_id=100500, first_name="Тест")


def _state(user: User, **payload: object) -> ConversationState:
    return ConversationState(
        id=uuid4(),
        user_id=user.id,
        flow=BOOKING_FLOW,
        step="vehicle_brand",
        payload={"appointment_id": str(uuid4()), **payload},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


async def test_select_brand_updates_appointment_and_state() -> None:
    user = _user()
    brand = VehicleBrand(id=uuid4(), name="Марка", is_active=True)
    state = _state(user)
    appointment = Appointment(
        id=uuid4(),
        user_id=user.id,
        status=AppointmentStatus.DRAFT,
        custom_vehicle_brand="Старая марка",
    )
    service = VehicleSelectionService(AsyncMock())
    service.brands.get_active = AsyncMock(return_value=brand)
    service._state_and_appointment = AsyncMock(return_value=(state, appointment))
    service._save_state = AsyncMock(return_value=state)

    await service.select_brand(user, BOOKING_FLOW, brand.id)

    assert appointment.vehicle_brand_id == brand.id
    assert appointment.custom_vehicle_brand is None
    _, step, payload = service._save_state.await_args.args
    assert step == "vehicle_model"
    assert payload["vehicle_brand_id"] == str(brand.id)


async def test_select_model_saves_model_and_its_vehicle_class() -> None:
    user = _user()
    brand_id = uuid4()
    class_id = uuid4()
    model = VehicleModel(
        id=uuid4(),
        brand_id=brand_id,
        vehicle_class_id=class_id,
        name="Модель",
        is_active=True,
    )
    state = _state(user, vehicle_brand_id=str(brand_id))
    appointment = Appointment(
        id=uuid4(), user_id=user.id, status=AppointmentStatus.DRAFT
    )
    service = VehicleSelectionService(AsyncMock())
    service._state_and_appointment = AsyncMock(return_value=(state, appointment))
    service.models.get_active_for_brand = AsyncMock(return_value=model)
    service._save_state = AsyncMock(return_value=state)

    await service.select_model(user, BOOKING_FLOW, model.id)

    assert appointment.vehicle_model_id == model.id
    assert appointment.vehicle_class_id == class_id
    _, step, payload = service._save_state.await_args.args
    assert step == "vehicle_year"
    assert payload["vehicle_class_id"] == str(class_id)


async def test_manual_input_removes_controls_and_is_saved() -> None:
    assert clean_user_text("  Land\n\x00 Rover  ", min_length=2) == "Land Rover"

    user = _user()
    state = _state(user)
    appointment = Appointment(
        id=uuid4(), user_id=user.id, status=AppointmentStatus.DRAFT
    )
    service = VehicleSelectionService(AsyncMock())
    service._state_and_appointment = AsyncMock(return_value=(state, appointment))
    service._save_state = AsyncMock(return_value=state)

    await service.save_custom_brand(user, BOOKING_FLOW, "  Другая\nмарка ")

    assert appointment.custom_vehicle_brand == "Другая марка"
    _, step, payload = service._save_state.await_args.args
    assert step == "custom_vehicle_model"
    assert payload["custom_vehicle_brand"] == "Другая марка"


async def test_single_vehicle_input_moves_directly_to_service_selection() -> None:
    user = _user()
    state = _state(user)
    appointment = Appointment(
        id=uuid4(), user_id=user.id, status=AppointmentStatus.DRAFT
    )
    service = VehicleSelectionService(AsyncMock())
    service._state_and_appointment = AsyncMock(return_value=(state, appointment))
    service._save_state = AsyncMock(return_value=state)

    await service.save_vehicle_description(user, BOOKING_FLOW, "  BMW\nX5  ")

    assert appointment.custom_vehicle_brand == "BMW X5"
    assert appointment.vehicle_model_id is None
    assert appointment.vehicle_class_id is None
    _, step, payload = service._save_state.await_args.args
    assert step == "service_selection"
    assert payload["custom_vehicle_brand"] == "BMW X5"


@pytest.mark.parametrize("raw", ["abcd", "1899", "9999", "20"])
async def test_invalid_year_is_rejected(raw: str) -> None:
    with pytest.raises(VehicleSelectionError):
        validate_vehicle_year(raw, now=datetime(2026, 1, 1, tzinfo=UTC))


async def test_back_from_models_returns_to_brands() -> None:
    user = _user()
    callback_message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=AsyncMock(), message=callback_message)
    callback_data = VehicleCallback(flow="b", entity="mo", action="back")
    service = Mock()
    service.set_step = AsyncMock()

    with (
        patch("app.bot.handlers.vehicle.VehicleSelectionService", return_value=service),
        patch("app.bot.handlers.vehicle.show_brands", new=AsyncMock()) as show_brands,
    ):
        session = AsyncMock()
        await handle_vehicle_callback(callback, callback_data, user, session)

    service.set_step.assert_awaited_once_with(
        user, BOOKING_FLOW, "vehicle_brand", model_search=None
    )
    show_brands.assert_awaited_once_with(callback_message, user, session, "b")


async def test_recovery_renders_saved_model_step() -> None:
    user = _user()
    state = _state(user, vehicle_brand_id=str(uuid4()))
    state.step = "vehicle_model"
    message = SimpleNamespace(answer=AsyncMock())

    with patch("app.bot.handlers.vehicle.show_models", new=AsyncMock()) as show_models:
        session = AsyncMock()
        await render_vehicle_step(message, user, session, state)

    show_models.assert_awaited_once_with(message, user, session, "b")


async def test_brand_keyboard_has_bounded_page_and_pagination() -> None:
    brands = [
        VehicleBrand(id=uuid4(), name=f"Марка {index}", is_active=True)
        for index in range(8)
    ]
    keyboard = brands_keyboard("b", Page(items=brands, page=0, pages=2, search=None))

    brand_buttons = [row[0] for row in keyboard.inline_keyboard[:8]]
    assert len(brand_buttons) == 8
    assert any(button.text == "→" for row in keyboard.inline_keyboard for button in row)


async def test_price_calculation_resumes_existing_state() -> None:
    user = _user()
    state = _state(user)
    state.flow = "price_calculation"
    service = VehicleSelectionService(AsyncMock())
    service.get_state = AsyncMock(return_value=state)
    service.states.upsert = AsyncMock()

    result = await service.start_price_calculation(user)

    assert result is state
    service.states.upsert.assert_not_awaited()
