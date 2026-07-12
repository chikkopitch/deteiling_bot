"""Safe update lifecycle logging."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Update

logger = logging.getLogger(__name__)


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        started = perf_counter()
        telegram_user = data.get("event_from_user")
        try:
            return await handler(event, data)
        finally:
            logger.info(
                "Telegram update processed; update_id=%s telegram_user_id=%s duration_ms=%.2f",
                event.update_id,
                getattr(telegram_user, "id", None),
                (perf_counter() - started) * 1000,
            )
