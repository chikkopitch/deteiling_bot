"""Last-resort Aiogram update error handler."""

from __future__ import annotations

import logging
from uuid import uuid4

from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)


async def handle_update_error(event: ErrorEvent) -> bool:
    """Log an unexpected update failure and return a safe response."""
    error_id = uuid4().hex[:12]
    logger.error(
        "Unhandled Telegram update error; error_id=%s update_id=%s",
        error_id,
        event.update.update_id,
        exc_info=(
            type(event.exception),
            event.exception,
            event.exception.__traceback__,
        ),
    )

    message = event.update.message
    if message is None and event.update.callback_query is not None:
        message = event.update.callback_query.message

    if message is not None:
        try:
            await message.answer(
                "Произошла внутренняя ошибка. Попробуйте ещё раз. "
                f"Код ошибки: <code>{error_id}</code>"
            )
        except Exception:
            logger.warning(
                "Could not send error response; error_id=%s",
                error_id,
                exc_info=True,
            )
    return True
