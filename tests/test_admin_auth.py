from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.database.enums import AdminRole
from app.database.models import Admin
from app.services.admin_auth import (
    AdminAccessDenied,
    AdminAuthorizationService,
    Permission,
)

pytestmark = pytest.mark.asyncio


def _admin(role: AdminRole, *, active: bool = True) -> Admin:
    return Admin(
        id=uuid4(),
        telegram_id=555,
        role=role,
        is_active=active,
    )


@pytest.mark.parametrize("permission", list(Permission))
async def test_owner_has_every_permission(permission: Permission) -> None:
    service = AdminAuthorizationService(AsyncMock())
    owner = _admin(AdminRole.OWNER)
    service.admins.get_by_telegram_id = AsyncMock(return_value=owner)

    assert await service.require(owner.telegram_id, permission) is owner


async def test_admin_can_manage_appointments_but_not_settings() -> None:
    service = AdminAuthorizationService(AsyncMock())
    admin = _admin(AdminRole.ADMIN)
    service.admins.get_by_telegram_id = AsyncMock(return_value=admin)

    assert (
        await service.require(admin.telegram_id, Permission.MANAGE_APPOINTMENTS)
        is admin
    )
    with pytest.raises(AdminAccessDenied):
        await service.require(admin.telegram_id, Permission.MANAGE_SETTINGS)


async def test_manager_can_view_but_cannot_confirm_application() -> None:
    service = AdminAuthorizationService(AsyncMock())
    manager = _admin(AdminRole.MANAGER)
    service.admins.get_by_telegram_id = AsyncMock(return_value=manager)

    assert (
        await service.require(manager.telegram_id, Permission.VIEW_APPOINTMENTS)
        is manager
    )
    with pytest.raises(AdminAccessDenied):
        await service.require(manager.telegram_id, Permission.MANAGE_APPOINTMENTS)


async def test_inactive_admin_is_denied() -> None:
    service = AdminAuthorizationService(AsyncMock())
    inactive = _admin(AdminRole.OWNER, active=False)
    service.admins.get_by_telegram_id = AsyncMock(return_value=inactive)

    with pytest.raises(AdminAccessDenied):
        await service.require(inactive.telegram_id, Permission.DASHBOARD)
