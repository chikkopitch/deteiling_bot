import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis
from redis.exceptions import RedisError
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
    redis: Redis | None = None
    if settings.REDIS_URL:
        redis_candidate = Redis.from_url(settings.REDIS_URL)
        try:
            await redis_candidate.ping()
        except RedisError as error:
            await log.awarning("redis_unavailable_using_memory_storage", error_type=type(error).__name__)
            await redis_candidate.aclose()
        else:
            redis = redis_candidate
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
