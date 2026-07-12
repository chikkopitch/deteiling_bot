from datetime import UTC, datetime, timedelta
from uuid import UUID
from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import CONTACT_MANAGER, main_menu_keyboard
from app.bot.keyboards.manager import (
    TOPICS,
    ManagerAdminCallback,
    ManagerUserCallback,
    manager_request_keyboard,
    photos_keyboard,
    review_keyboard,
    topics_keyboard,
)
from app.database.enums import AdminRole
from app.database.models import ConversationState, ManagerRequest, User
from app.database.repositories import AdminRepository, ConversationStateRepository
from app.services.admin_auth import (
    AdminAccessDenied,
    AdminAuthorizationService,
    Permission,
)
from app.services.manager_requests import ManagerRequestService
from app.services.vehicle_selection import VehicleSelectionError, clean_user_text

router = Router(name="manager_requests")
FLOW = "manager_request"
ADMIN_FLOW = "manager_work"


async def start(message, user, session):
    await ConversationStateRepository(session).upsert(
        user_id=user.id,
        flow=FLOW,
        step="topic",
        payload={},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    await message.answer("Выберите тему обращения:", reply_markup=topics_keyboard())


@router.message(F.text == CONTACT_MANAGER)
async def begin(message: Message, app_user: User, session: AsyncSession):
    await start(message, app_user, session)


class Step(BaseFilter):
    def __init__(self, step):
        self.step = step

    async def __call__(self, message, app_user, session):
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, FLOW, datetime.now(UTC)
        )
        return {"manager_state": state} if state and state.step == self.step else False


@router.callback_query(ManagerUserCallback.filter())
async def user_callback(
    callback: CallbackQuery,
    callback_data: ManagerUserCallback,
    app_user: User,
    session: AsyncSession,
    bot: Bot,
):
    await callback.answer()
    state = await ConversationStateRepository(session).get_active_for_flow(
        app_user.id, FLOW, datetime.now(UTC)
    )
    if callback.message is None:
        return
    if callback_data.action in {"cancel", "restart"}:
        if state:
            await session.delete(state)
        if callback_data.action == "restart":
            return await start(callback.message, app_user, session)
        return await callback.message.answer(
            "Обращение отменено.", reply_markup=main_menu_keyboard()
        )
    if state is None:
        return await callback.message.answer("Сценарий истёк.")
    payload = dict(state.payload)
    if callback_data.action == "topic" and callback_data.value in TOPICS:
        payload["topic"] = TOPICS[callback_data.value]
        await ConversationStateRepository(session).upsert(
            user_id=app_user.id,
            flow=FLOW,
            step="message",
            payload=payload,
            expires_at=state.expires_at,
        )
        await callback.message.answer(
            "Опишите вопрос сообщением от 3 до 2000 символов:"
        )
    elif callback_data.action == "review":
        await ConversationStateRepository(session).upsert(
            user_id=app_user.id,
            flow=FLOW,
            step="review",
            payload=payload,
            expires_at=state.expires_at,
        )
        await callback.message.answer(
            f"Тема: {payload['topic']}\nСообщение: {payload['message']}\nФото: {len(payload.get('photos', []))}",
            reply_markup=review_keyboard(),
        )
    elif callback_data.action == "submit" and state.step == "review":
        request = await ManagerRequestService(session).create(
            app_user, payload["topic"], payload["message"], payload.get("photos", [])
        )
        await session.delete(state)
        await session.commit()
        managers = await AdminRepository(session).list_active(AdminRole.MANAGER)
        for manager in managers:
            try:
                await bot.send_message(
                    manager.telegram_id,
                    f"Новое обращение #{str(request.id)[:8]}\nТема: {request.topic}\n{request.message}",
                    reply_markup=manager_request_keyboard(request.id),
                )
            except Exception:
                pass
        await callback.message.answer(
            "Обращение отправлено менеджеру.", reply_markup=main_menu_keyboard()
        )


@router.message(F.text & ~F.text.startswith("/"), Step("message"))
async def receive_message(
    message: Message,
    manager_state: ConversationState,
    app_user: User,
    session: AsyncSession,
):
    try:
        text = clean_user_text(message.text, min_length=3, max_length=2000)
    except VehicleSelectionError as error:
        return await message.answer(str(error))
    payload = dict(manager_state.payload)
    payload.update(message=text, photos=[])
    await ConversationStateRepository(session).upsert(
        user_id=app_user.id,
        flow=FLOW,
        step="photos",
        payload=payload,
        expires_at=manager_state.expires_at,
    )
    await message.answer(
        "Приложите до 5 фотографий или нажмите «Пропустить».",
        reply_markup=photos_keyboard(),
    )


@router.message(F.photo, Step("photos"))
async def receive_photo(
    message: Message,
    manager_state: ConversationState,
    app_user: User,
    session: AsyncSession,
):
    photos = list(manager_state.payload.get("photos", []))
    file_id = message.photo[-1].file_id
    if file_id not in photos and len(photos) < 5:
        photos.append(file_id)
    payload = dict(manager_state.payload)
    payload["photos"] = photos
    await ConversationStateRepository(session).upsert(
        user_id=app_user.id,
        flow=FLOW,
        step="photos",
        payload=payload,
        expires_at=manager_state.expires_at,
    )
    await message.answer(
        f"Загружено фотографий: {len(photos)} из 5", reply_markup=photos_keyboard()
    )


class AdminReplyFilter(BaseFilter):
    async def __call__(self, message, app_user, session):
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, ADMIN_FLOW, datetime.now(UTC)
        )
        return (
            {"admin_manager_state": state} if state and state.step == "reply" else False
        )


@router.callback_query(ManagerAdminCallback.filter())
async def admin_callback(
    callback: CallbackQuery,
    callback_data: ManagerAdminCallback,
    app_user: User,
    session: AsyncSession,
):
    try:
        admin = await AdminAuthorizationService(session).require(
            callback.from_user.id, Permission.MANAGE_REQUESTS
        )
    except AdminAccessDenied as error:
        return await callback.answer(str(error), show_alert=True)
    service = ManagerRequestService(session)
    action = callback_data.action
    if action == "open":
        request = await session.get(ManagerRequest, callback_data.request_id)
        if request is None:
            return await callback.answer("Обращение не найдено", show_alert=True)
        await callback.message.answer(
            f"Обращение #{str(request.id)[:8]}\nТема: {request.topic}\nСтатус: {request.status.value}\n{request.message}",
            reply_markup=manager_request_keyboard(request.id),
        )
        return await callback.answer()
    elif action == "assign":
        await service.assign(callback_data.request_id, admin)
    elif action == "close":
        await service.close(callback_data.request_id, admin)
    elif action == "reopen":
        await service.reopen(callback_data.request_id, admin)
    elif action in {"reply", "transfer"}:
        await ConversationStateRepository(session).upsert(
            user_id=app_user.id,
            flow=ADMIN_FLOW,
            step=action,
            payload={"request_id": str(callback_data.request_id)},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await callback.message.answer(
            "Введите ответ клиенту:"
            if action == "reply"
            else "Выберите сотрудника в следующем сообщении командой /transfer TELEGRAM_ID"
        )
        return await callback.answer()
    await callback.answer("Готово")


@router.message(F.text.startswith("/transfer "))
async def transfer_request(message: Message, app_user: User, session: AsyncSession):
    try:
        await AdminAuthorizationService(session).require(
            message.from_user.id, Permission.MANAGE_REQUESTS
        )
    except AdminAccessDenied as error:
        return await message.answer(str(error))
    state = await ConversationStateRepository(session).get_active_for_flow(
        app_user.id, ADMIN_FLOW, datetime.now(UTC)
    )
    if state is None or state.step != "transfer":
        return
    try:
        telegram_id = int((message.text or "").split(maxsplit=1)[1])
    except (ValueError, IndexError):
        return await message.answer("Формат: /transfer TELEGRAM_ID")
    target = await AdminRepository(session).get_by_telegram_id(telegram_id)
    if target is None:
        return await message.answer("Сотрудник не найден.")
    await ManagerRequestService(session).transfer(
        UUID(state.payload["request_id"]), target
    )
    await session.delete(state)
    await message.answer("Обращение передано.")


@router.message((F.text | F.photo), AdminReplyFilter())
async def admin_reply(
    message: Message,
    admin_manager_state: ConversationState,
    app_user: User,
    session: AsyncSession,
    bot: Bot,
):
    try:
        admin = await AdminAuthorizationService(session).require(
            message.from_user.id, Permission.MANAGE_REQUESTS
        )
    except AdminAccessDenied as error:
        return await message.answer(str(error))
    photo = message.photo[-1].file_id if message.photo else None
    result = await ManagerRequestService(session).reply(
        UUID(admin_manager_state.payload["request_id"]),
        admin,
        bot,
        text=message.caption if photo else message.text,
        file_id=photo,
    )
    await session.delete(admin_manager_state)
    await message.answer(f"Статус доставки: {result.delivery_status}.")
