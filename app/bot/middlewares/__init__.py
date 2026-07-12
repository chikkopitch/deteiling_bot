"""Custom Aiogram middlewares."""

from app.bot.middlewares.blocked import BlockedUserMiddleware
from app.bot.middlewares.database import DatabaseSessionMiddleware
from app.bot.middlewares.logging import UpdateLoggingMiddleware
from app.bot.middlewares.user import UserRegistrationMiddleware

__all__ = [
    "BlockedUserMiddleware",
    "DatabaseSessionMiddleware",
    "UpdateLoggingMiddleware",
    "UserRegistrationMiddleware",
]
