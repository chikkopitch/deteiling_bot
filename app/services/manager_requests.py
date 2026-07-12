"""Manager request lifecycle and Telegram delivery tracking."""

from datetime import UTC, datetime
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import ManagerRequestStatus, SenderType
from app.database.models import Admin, ManagerRequest, ManagerRequestMessage, User
from app.services.vehicle_selection import VehicleSelectionError, clean_user_text


class ManagerRequestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user: User,
        topic: str,
        message: str,
        photos: list[str],
        appointment_id: UUID | None = None,
    ):
        topic = clean_user_text(topic, min_length=2, max_length=160)
        message = clean_user_text(message, min_length=3, max_length=2000)
        request = ManagerRequest(
            user_id=user.id,
            appointment_id=appointment_id,
            topic=topic,
            message=message,
            status=ManagerRequestStatus.OPEN,
        )
        self.session.add(request)
        await self.session.flush()
        self.session.add(
            ManagerRequestMessage(
                request_id=request.id,
                sender_type=SenderType.USER,
                sender_user_id=user.id,
                text=message,
            )
        )
        for file_id in photos[:5]:
            self.session.add(
                ManagerRequestMessage(
                    request_id=request.id,
                    sender_type=SenderType.USER,
                    sender_user_id=user.id,
                    telegram_file_id=file_id,
                )
            )
        await self.session.flush()
        return request

    async def get_for_update(self, request_id):
        result = await self.session.execute(
            select(ManagerRequest)
            .where(ManagerRequest.id == request_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise VehicleSelectionError("Обращение не найдено.")
        return request

    async def assign(self, request_id, admin: Admin):
        request = await self.get_for_update(request_id)
        request.assigned_admin_id = admin.id
        request.status = ManagerRequestStatus.ASSIGNED
        return request

    async def close(self, request_id, admin: Admin):
        request = await self.get_for_update(request_id)
        if request.assigned_admin_id not in {None, admin.id}:
            raise VehicleSelectionError("Обращение назначено другому сотруднику.")
        request.assigned_admin_id = admin.id
        request.status = ManagerRequestStatus.CLOSED
        request.closed_at = datetime.now(UTC)
        return request

    async def reopen(self, request_id, admin: Admin):
        request = await self.get_for_update(request_id)
        request.status = ManagerRequestStatus.ASSIGNED
        request.assigned_admin_id = admin.id
        request.closed_at = None
        return request

    async def transfer(self, request_id, target: Admin):
        if not target.is_active:
            raise VehicleSelectionError("Сотрудник неактивен.")
        request = await self.get_for_update(request_id)
        request.assigned_admin_id = target.id
        request.status = ManagerRequestStatus.ASSIGNED
        return request

    async def reply(
        self,
        request_id,
        admin: Admin,
        bot: Bot,
        *,
        text: str | None = None,
        file_id: str | None = None,
    ):
        if not text and not file_id:
            raise VehicleSelectionError("Ответ пуст.")
        if text:
            text = clean_user_text(text, min_length=1, max_length=4000)
        request = await self.get_for_update(request_id)
        if request.status in {
            ManagerRequestStatus.CLOSED,
            ManagerRequestStatus.CANCELLED,
        }:
            raise VehicleSelectionError("Обращение закрыто.")
        if request.assigned_admin_id not in {None, admin.id}:
            raise VehicleSelectionError("Обращение назначено другому сотруднику.")
        request.assigned_admin_id = admin.id
        request.status = ManagerRequestStatus.WAITING_CUSTOMER
        message = ManagerRequestMessage(
            request_id=request.id,
            sender_type=SenderType.ADMIN,
            sender_admin_id=admin.id,
            text=text,
            telegram_file_id=file_id,
            delivery_status="pending",
        )
        self.session.add(message)
        await self.session.flush()
        user = await self.session.get(User, request.user_id)
        if user is None:
            raise VehicleSelectionError("Пользователь не найден.")
        try:
            if file_id:
                await bot.send_photo(user.telegram_id, file_id, caption=text)
            else:
                await bot.send_message(user.telegram_id, text)
            message.delivery_status = "sent"
            message.delivered_at = datetime.now(UTC)
            message.delivery_error = None
        except TelegramForbiddenError as error:
            user.is_blocked = True
            message.delivery_status = "blocked"
            message.delivery_error = str(error)[:1000]
        except TelegramAPIError as error:
            message.delivery_status = "failed"
            message.delivery_error = str(error)[:1000]
        await self.session.flush()
        return message
