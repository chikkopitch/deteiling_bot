from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.fallback import old_callback
from app.bot.handlers.start import cancel, menu, start
from app.bot.keyboards import navigation


@pytest.mark.asyncio
async def test_start_shows_welcome_and_main_menu() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await start(message, state)  # type: ignore[arg-type]

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "Бесплатный осмотр" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_menu_and_cancel_clear_fsm_and_edit_message() -> None:
    message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(message=message, answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await menu(callback, state)  # type: ignore[arg-type]
    await cancel(callback, state)  # type: ignore[arg-type]

    assert state.clear.await_count == 2
    assert message.edit_text.await_count == 2
    assert callback.answer.await_count == 2


@pytest.mark.asyncio
async def test_unknown_callback_is_handled_safely() -> None:
    callback = SimpleNamespace(answer=AsyncMock())

    await old_callback(callback)  # type: ignore[arg-type]

    callback.answer.assert_awaited_once_with(
        "Эта кнопка устарела. Откройте меню заново.", show_alert=True
    )


def test_navigation_has_back_cancel_and_main_menu() -> None:
    buttons = [button.text for row in navigation(back="services", cancel=True) for button in row]
    assert buttons == ["← Назад", "Отменить", "Главное меню"]
