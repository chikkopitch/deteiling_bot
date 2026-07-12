import structlog
from aiogram import Router
from aiogram.types import ErrorEvent, Message

log = structlog.get_logger()
router = Router(name="errors")


@router.errors()
async def global_error_handler(event: ErrorEvent) -> bool:
    """Log internal details and show users a neutral message."""
    await log.aexception("telegram_update_failed", error_type=type(event.exception).__name__)
    message = event.update.message
    callback = event.update.callback_query
    if message is None and callback is not None and isinstance(callback.message, Message):
        message = callback.message
    if message:
        await message.answer("Произошла временная ошибка. Пожалуйста, повторите попытку позже.")
    if callback:
        await callback.answer()
    return True
