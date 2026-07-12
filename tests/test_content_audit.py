from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from app.database.enums import AdminRole
from app.database.models import Admin, ContentSetting
from app.services.content_admin import ContentAdminService

pytestmark = pytest.mark.asyncio


async def test_content_preview_does_not_write_before_confirmation():
    service = ContentAdminService(AsyncMock())
    service.content.get_by_key = AsyncMock(
        return_value=ContentSetting(id=uuid4(), key="welcome_text", value="Старое")
    )
    service.audit.add = AsyncMock()
    preview = await service.preview("welcome_text", "Новое")
    assert preview.old_value == "Старое" and preview.new_value == "Новое"
    service.audit.add.assert_not_awaited()


async def test_confirmed_content_change_writes_audit():
    setting = ContentSetting(id=uuid4(), key="welcome_text", value="Старое")
    admin = Admin(id=uuid4(), telegram_id=1, role=AdminRole.OWNER, is_active=True)
    service = ContentAdminService(AsyncMock())
    service.content.get_by_key = AsyncMock(return_value=setting)
    service.audit.add = AsyncMock()
    preview = await service.preview("welcome_text", "Новое")
    await service.save(admin, preview)
    assert setting.value == "Новое"
    audit = service.audit.add.await_args.args[0]
    assert (
        audit.admin_id == admin.id
        and audit.old_value == {"value": "Старое"}
        and audit.new_value == {"value": "Новое"}
    )
