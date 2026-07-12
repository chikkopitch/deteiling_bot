"""Container readiness check for required persistence services."""

import asyncio

from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.database import Database


async def check() -> None:
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    redis = Redis.from_url(settings.REDIS_URL)
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
        await redis.ping()
    finally:
        await redis.aclose()
        await database.close()


if __name__ == "__main__":
    asyncio.run(check())
