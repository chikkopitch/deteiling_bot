import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis
from redis.exceptions import RedisError

log = structlog.get_logger()


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        await log.ainfo(
            "telegram_update_received",
            update_type=type(event).__name__,
            telegram_id=user.id if user else None,
        )
        return await handler(event, data)


class ContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=str(uuid4()))
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, period: float = 0.35) -> None:
        self.redis, self.period = redis, period

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            key = f"throttle:{user.id}"
            try:
                allowed = await self.redis.set(
                    key, str(time.time()), ex=max(1, int(self.period) + 1), nx=True
                )
            except RedisError as error:
                await log.awarning("throttle_redis_unavailable", error_type=type(error).__name__)
                allowed = True
            if not allowed:
                return None
        return await handler(event, data)
