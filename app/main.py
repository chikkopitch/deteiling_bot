"""Application composition root and process lifecycle."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Callable

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import get_root_router
from app.bot.middlewares import (
    BlockedUserMiddleware,
    DatabaseSessionMiddleware,
    UpdateLoggingMiddleware,
    UserRegistrationMiddleware,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import install_asyncio_exception_handler
from app.core.logging import configure_logging
from app.database.session import Database, create_database
from app.scheduler import reminder_scheduler_loop, reservation_cleanup_loop

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    """Create a configured Telegram Bot API client."""
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Create Dispatcher and attach all application routers and hooks."""
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(UpdateLoggingMiddleware())
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    dispatcher.update.outer_middleware(UserRegistrationMiddleware())
    dispatcher.update.outer_middleware(BlockedUserMiddleware())
    dispatcher.include_router(get_root_router())
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    return dispatcher


async def on_startup(
    bot: Bot,
    database: Database,
    settings: Settings,
    **_: object,
) -> None:
    """Validate external dependencies immediately before polling."""
    await database.check_connection()
    bot_info = await bot.get_me()
    logger.info(
        "Application started",
        extra={
            "bot_id": bot_info.id,
            "bot_username": bot_info.username,
            "timezone": settings.app_timezone.key,
        },
    )


async def on_shutdown(**_: object) -> None:
    """Log Dispatcher shutdown; owned resources close in main()."""
    logger.info("Dispatcher shutdown hook completed")


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    stop_callback: Callable[[str], None],
) -> list[tuple[signal.Signals, object]]:
    """Install portable SIGINT/SIGTERM handlers and return previous handlers."""
    previous: list[tuple[signal.Signals, object]] = []

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handler = signal.getsignal(sig)
        previous.append((sig, previous_handler))

        try:
            loop.add_signal_handler(sig, stop_callback, sig.name)
        except (NotImplementedError, RuntimeError):
            signal.signal(
                sig,
                lambda received, _frame, name=sig.name: loop.call_soon_threadsafe(
                    stop_callback, name
                ),
            )

    return previous


def _restore_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    previous: list[tuple[signal.Signals, object]],
) -> None:
    for sig, previous_handler in previous:
        try:
            loop.remove_signal_handler(sig)
        except (NotImplementedError, RuntimeError):
            pass
        signal.signal(sig, previous_handler)


async def main() -> None:
    """Build the application, run polling, and close all owned resources."""
    settings = get_settings()
    configure_logging(settings.log_level)
    install_asyncio_exception_handler()

    database = create_database(settings)
    bot = create_bot(settings)
    dispatcher = create_dispatcher()
    loop = asyncio.get_running_loop()
    shutdown_requested = False

    async def stop_polling_safely() -> None:
        try:
            await dispatcher.stop_polling()
        except RuntimeError:
            logger.debug("Polling was not active when shutdown was requested")

    def request_shutdown(signal_name: str) -> None:
        nonlocal shutdown_requested
        if shutdown_requested:
            return
        shutdown_requested = True
        logger.info("Shutdown requested", extra={"signal": signal_name})
        asyncio.create_task(
            stop_polling_safely(),
            name=f"stop-polling-{signal_name.lower()}",
        )

    previous_handlers = _install_signal_handlers(loop, request_shutdown)
    scheduler_stop = asyncio.Event()
    scheduler_task: asyncio.Task[None] | None = None
    reminder_task: asyncio.Task[None] | None = None

    try:
        # Fail before opening long polling when PostgreSQL is unavailable.
        await database.check_connection()
        scheduler_task = asyncio.create_task(
            reservation_cleanup_loop(
                database.session_factory,
                scheduler_stop,
                interval_seconds=settings.reservation_cleanup_seconds,
            ),
            name="reservation-cleanup",
        )
        reminder_task = asyncio.create_task(
            reminder_scheduler_loop(
                database.session_factory,
                bot,
                settings,
                scheduler_stop,
            ),
            name="reminder-scheduler",
        )
        await dispatcher.start_polling(
            bot,
            database=database,
            session_factory=database.session_factory,
            settings=settings,
            handle_signals=False,
            close_bot_session=False,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        scheduler_stop.set()
        if scheduler_task is not None:
            await scheduler_task
        if reminder_task is not None:
            await reminder_task
        _restore_signal_handlers(loop, previous_handlers)
        await bot.session.close()
        await database.dispose()
        logger.info("Application resources closed")


def run() -> None:
    """Synchronous launcher used by start.py."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Fallback for platforms where the event loop cannot own SIGINT.
        logging.getLogger(__name__).info("Application interrupted")
    except Exception:
        logging.getLogger(__name__).critical(
            "Application terminated by an unrecoverable error",
            exc_info=True,
        )
        sys.exit(1)
