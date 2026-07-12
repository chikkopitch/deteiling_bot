from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.bot.handlers.start import continue_draft, handle_start
from app.bot.keyboards import DraftActionCallback
from app.bot.middlewares.blocked import BLOCKED_MESSAGE, BlockedUserMiddleware
from app.bot.middlewares.user import UserRegistrationMiddleware
from app.database.enums import AppointmentStatus
from app.database.models import Appointment, ConversationState, User
from app.services.user_entry import EntryContext

pytestmark = pytest.mark.asyncio


def _user(*, blocked: bool = False) -> User:
    return User(
        id=uuid4(),
        telegram_id=123456789,
        first_name="Иван",
        is_blocked=blocked,
    )


async def test_start_without_draft_shows_welcome_and_main_menu() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    app_user = _user()
    service = Mock()
    service.load_context = AsyncMock(
        return_value=EntryContext(
            welcome_text="Текст из content_settings",
            draft=None,
            state=None,
        )
    )

    with patch("app.bot.handlers.start.UserEntryService", return_value=service):
        await handle_start(message, app_user, AsyncMock())

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert args[0] == "Текст из content_settings"
    button_texts = {
        button.text for row in kwargs["reply_markup"].keyboard for button in row
    }
    assert button_texts == {
        "Записаться на бесплатный осмотр",
        "Рассчитать стоимость",
        "Услуги",
        "Мои записи",
        "Частые вопросы",
        "Связаться с менеджером",
    }


async def test_start_with_draft_offers_recovery_actions() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    app_user = _user()
    draft = Appointment(
        id=uuid4(),
        user_id=app_user.id,
        status=AppointmentStatus.DRAFT,
    )
    state = ConversationState(
        id=uuid4(),
        user_id=app_user.id,
        flow="booking",
        step="vehicle_model",
        payload={"appointment_id": str(draft.id)},
        expires_at=SimpleNamespace(),  # not evaluated by this handler test
    )
    service = Mock()
    service.load_context = AsyncMock(
        return_value=EntryContext(
            welcome_text="Добро пожаловать",
            draft=draft,
            state=state,
        )
    )

    with patch("app.bot.handlers.start.UserEntryService", return_value=service):
        await handle_start(message, app_user, AsyncMock())

    args, kwargs = message.answer.await_args
    assert "незавершённая заявка" in args[0]
    button_texts = [
        button.text for row in kwargs["reply_markup"].inline_keyboard for button in row
    ]
    assert button_texts == ["Продолжить", "Начать заново", "Удалить черновик"]


async def test_continue_restores_saved_draft_step() -> None:
    app_user = _user()
    draft = Appointment(id=uuid4(), user_id=app_user.id, status=AppointmentStatus.DRAFT)
    state = ConversationState(
        id=uuid4(),
        user_id=app_user.id,
        flow="booking",
        step="vehicle_model",
        payload={"appointment_id": str(draft.id)},
        expires_at=SimpleNamespace(),
    )
    callback_message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=AsyncMock(), message=callback_message)
    service = Mock()
    service.resume_booking = AsyncMock(return_value=(draft, state))
    callback_data = DraftActionCallback(action="continue", appointment_id=draft.id)

    with (
        patch("app.bot.handlers.start.UserEntryService", return_value=service),
        patch(
            "app.bot.handlers.vehicle.render_vehicle_step", new=AsyncMock()
        ) as render,
    ):
        session = AsyncMock()
        await continue_draft(callback, callback_data, app_user, session)

    service.resume_booking.assert_awaited_once_with(app_user, draft.id)
    callback.answer.assert_awaited_once()
    callback_message.answer.assert_awaited_once_with("Черновик восстановлен.")
    render.assert_awaited_once_with(callback_message, app_user, session, state)


async def test_blocked_user_is_stopped_before_handler() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    update = SimpleNamespace(message=message, callback_query=None)
    next_handler = AsyncMock()

    result = await BlockedUserMiddleware()(
        next_handler,
        update,
        {"app_user": _user(blocked=True)},
    )

    assert result is None
    next_handler.assert_not_awaited()
    message.answer.assert_awaited_once_with(BLOCKED_MESSAGE)


async def test_registration_uses_numeric_telegram_id_and_upsert() -> None:
    telegram_user = SimpleNamespace(
        id=987654321,
        username="changeable_username",
        first_name="Иван",
        last_name="Иванов",
    )
    registered_user = _user()
    repository = Mock()
    repository.upsert_telegram_profile = AsyncMock(return_value=registered_user)
    next_handler = AsyncMock(return_value="handled")
    data = {"event_from_user": telegram_user, "session": AsyncMock()}

    with patch("app.bot.middlewares.user.UserRepository", return_value=repository):
        result = await UserRegistrationMiddleware()(next_handler, Mock(), data)

    assert result == "handled"
    repository.upsert_telegram_profile.assert_awaited_once_with(
        telegram_id=987654321,
        username="changeable_username",
        first_name="Иван",
        last_name="Иванов",
    )
    assert data["app_user"] is registered_user
