import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis
from sqlalchemy import text

from app.bot.handlers import root_router
from app.bot.middlewares import (
    ContextMiddleware,
    DatabaseMiddleware,
    LoggingMiddleware,
    ThrottleMiddleware,
)
from app.config import Settings, get_settings
from app.database import Database
from app.scheduler import NotificationWorker
from app.utils.logging import configure_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(
    settings: Settings,
) -> AsyncIterator[tuple[Bot, Dispatcher, Database, Redis | None]]:
    configure_logging(settings.LOG_LEVEL)
    database = Database(settings.DATABASE_URL)
    redis = Redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
    bot = Bot(settings.BOT_TOKEN)
    dispatcher = Dispatcher(storage=RedisStorage(redis) if redis else MemoryStorage())
    scheduler = AsyncIOScheduler(timezone="UTC")
    worker = NotificationWorker(database, bot, settings)
    dispatcher.update.outer_middleware(DatabaseMiddleware(database))
    dispatcher.update.outer_middleware(LoggingMiddleware())
    dispatcher.update.outer_middleware(ContextMiddleware())
    if redis:
        dispatcher.update.outer_middleware(ThrottleMiddleware(redis))
    dispatcher["settings"] = settings
    dispatcher.include_router(root_router(settings))
    scheduler.add_job(
        worker.run, "interval", seconds=30, id="notification-worker", max_instances=1, coalesce=True
    )
    scheduler.start()
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
        if redis:
            await redis.ping()
        yield bot, dispatcher, database, redis
    finally:
        scheduler.shutdown(wait=False)
        await dispatcher.storage.close()
        await bot.session.close()
        if redis:
            await redis.aclose()
        await database.close()


async def main() -> None:
    settings = get_settings()
    async with lifespan(settings) as (bot, dispatcher, _, _):
        await log.ainfo("bot_started", studio=settings.STUDIO_NAME)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
