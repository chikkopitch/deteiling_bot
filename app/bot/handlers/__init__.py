"""Router assembly."""

from aiogram import Router

from app.bot.handlers.errors import handle_update_error
from app.bot.handlers.common import router as common_router
from app.bot.handlers.menu import router as menu_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.services import router as services_selection_router
from app.bot.handlers.schedule import router as schedule_router
from app.bot.handlers.contacts import router as contacts_router
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.my_appointments import router as my_appointments_router
from app.bot.handlers.content import router as content_router
from app.bot.handlers.manager import router as manager_router
from app.bot.handlers.vehicle import router as vehicle_router


def get_root_router() -> Router:
    """Build the application router tree in deterministic order."""
    router = Router(name="root")
    router.errors.register(handle_update_error)
    router.include_router(start_router)
    router.include_router(admin_router)
    router.include_router(my_appointments_router)
    router.include_router(content_router)
    router.include_router(manager_router)
    router.include_router(menu_router)
    router.include_router(vehicle_router)
    router.include_router(services_selection_router)
    router.include_router(schedule_router)
    router.include_router(contacts_router)
    router.include_router(common_router)
    return router


__all__ = ["get_root_router"]
