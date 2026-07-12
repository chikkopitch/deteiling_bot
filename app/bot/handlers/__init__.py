from aiogram import Router

from app.bot.handlers import admin, booking, catalog, errors, extras, fallback, start
from app.config import Settings


def root_router(settings: Settings) -> Router:
    admin.setup(settings)
    router = Router(name="root")
    router.include_router(errors.router)
    router.include_routers(
        admin.router, start.router, booking.router, catalog.router, extras.router, fallback.router
    )
    return router
