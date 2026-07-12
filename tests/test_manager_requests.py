from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from aiogram.exceptions import TelegramForbiddenError
from app.database.enums import AdminRole, ManagerRequestStatus, SenderType
from app.database.models import Admin, ManagerRequest, User
from app.services.manager_requests import ManagerRequestService

pytestmark = pytest.mark.asyncio


async def test_create_request_and_first_message_with_photos():
    session = AsyncMock()
    session.add = lambda value: added.append(value)
    added = []
    user = User(id=uuid4(), telegram_id=1)
    service = ManagerRequestService(session)
    request = await service.create(
        user, "Стоимость", "Нужна консультация", ["f1", "f2"]
    )
    assert request.status == ManagerRequestStatus.OPEN
    messages = [x for x in added if x.__class__.__name__ == "ManagerRequestMessage"]
    assert len(messages) == 3
    assert (
        messages[0].sender_type == SenderType.USER
        and messages[0].text == "Нужна консультация"
    )


async def test_manager_assign_close_and_reopen():
    request = ManagerRequest(
        id=uuid4(),
        user_id=uuid4(),
        topic="Услуга",
        message="Вопрос",
        status=ManagerRequestStatus.OPEN,
    )
    admin = Admin(id=uuid4(), telegram_id=2, role=AdminRole.MANAGER, is_active=True)
    service = ManagerRequestService(AsyncMock())
    service.get_for_update = AsyncMock(return_value=request)
    await service.assign(request.id, admin)
    assert request.assigned_admin_id == admin.id
    await service.close(request.id, admin)
    assert (
        request.status == ManagerRequestStatus.CLOSED and request.closed_at is not None
    )
    await service.reopen(request.id, admin)
    assert request.status == ManagerRequestStatus.ASSIGNED and request.closed_at is None


async def test_blocked_bot_delivery_is_saved_and_user_blocked():
    user = User(id=uuid4(), telegram_id=7, is_blocked=False)
    request = ManagerRequest(
        id=uuid4(),
        user_id=user.id,
        topic="Другое",
        message="Вопрос",
        status=ManagerRequestStatus.OPEN,
    )
    admin = Admin(id=uuid4(), telegram_id=2, role=AdminRole.MANAGER, is_active=True)
    session = AsyncMock()
    session.add = lambda value: None
    session.get = AsyncMock(return_value=user)
    service = ManagerRequestService(session)
    service.get_for_update = AsyncMock(return_value=request)
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(
        method=AsyncMock(), message="bot was blocked"
    )
    result = await service.reply(request.id, admin, bot, text="Ответ")
    assert result.delivery_status == "blocked"
    assert user.is_blocked is True


async def test_successful_delivery_status_is_saved():
    user = User(id=uuid4(), telegram_id=7)
    request = ManagerRequest(
        id=uuid4(),
        user_id=user.id,
        topic="Другое",
        message="Вопрос",
        status=ManagerRequestStatus.OPEN,
    )
    admin = Admin(id=uuid4(), telegram_id=2, role=AdminRole.MANAGER, is_active=True)
    session = AsyncMock()
    session.add = lambda value: None
    session.get = AsyncMock(return_value=user)
    service = ManagerRequestService(session)
    service.get_for_update = AsyncMock(return_value=request)
    result = await service.reply(request.id, admin, AsyncMock(), text="Ответ")
    assert result.delivery_status == "sent" and result.delivered_at is not None
