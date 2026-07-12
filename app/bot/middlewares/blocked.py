"""Stop blocked customers before application handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Update

from app.database.models import User

BLOCKED_MESSAGE = (
    "Доступ к боту ограничен. Если вы считаете, что это ошибка, "
    "свяжитесь с менеджером студии другим доступным способом."
)


class BlockedUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        app_user: User | None = data.get("app_user")
        if app_user is None or not app_user.is_blocked:
            return await handler(event, data)

        if event.callback_query is not None:
            await event.callback_query.answer(BLOCKED_MESSAGE, show_alert=True)
        elif event.message is not None:
            await event.message.answer(BLOCKED_MESSAGE)
        return None
