from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database import Database
from app.repositories import UserRepository


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, database: Database) -> None:
        self.database = database

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.database.session_factory() as session:
            data["session"] = session
            user = getattr(event, "from_user", None)
            if user:
                data["db_user"] = await UserRepository(session).upsert_telegram(
                    user.id, user.username, user.first_name, user.last_name
                )
                await session.commit()
            return await handler(event, data)
