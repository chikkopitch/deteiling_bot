"""Database-resolved role permissions for every administrative action."""

from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import AdminRole
from app.database.models import Admin
from app.database.repositories import AdminRepository


class Permission(StrEnum):
    DASHBOARD = "dashboard"
    VIEW_APPOINTMENTS = "view_appointments"
    MANAGE_APPOINTMENTS = "manage_appointments"
    MANAGE_SCHEDULE = "manage_schedule"
    MANAGE_SERVICES = "manage_services"
    MANAGE_PRICES = "manage_prices"
    MANAGE_FAQ = "manage_faq"
    VIEW_CLIENTS = "view_clients"
    MANAGE_REQUESTS = "manage_requests"
    VIEW_STATISTICS = "view_statistics"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_ADMINS = "manage_admins"
    VIEW_AUDIT = "view_audit"


ROLE_PERMISSIONS: dict[AdminRole, frozenset[Permission]] = {
    AdminRole.OWNER: frozenset(Permission),
    AdminRole.ADMIN: frozenset(
        {
            Permission.DASHBOARD,
            Permission.VIEW_APPOINTMENTS,
            Permission.MANAGE_APPOINTMENTS,
            Permission.MANAGE_SCHEDULE,
            Permission.MANAGE_SERVICES,
            Permission.MANAGE_PRICES,
            Permission.MANAGE_FAQ,
            Permission.VIEW_CLIENTS,
            Permission.VIEW_STATISTICS,
        }
    ),
    AdminRole.MANAGER: frozenset(
        {
            Permission.DASHBOARD,
            Permission.VIEW_APPOINTMENTS,
            Permission.MANAGE_REQUESTS,
        }
    ),
}


class AdminAccessDenied(PermissionError):
    pass


class AdminAuthorizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.admins = AdminRepository(session)

    async def require(self, telegram_id: int, permission: Permission) -> Admin:
        admin = await self.admins.get_by_telegram_id(telegram_id)
        if admin is None or not admin.is_active:
            raise AdminAccessDenied("Административный доступ запрещён.")
        if permission not in ROLE_PERMISSIONS[admin.role]:
            raise AdminAccessDenied("Недостаточно прав для этого действия.")
        return admin
