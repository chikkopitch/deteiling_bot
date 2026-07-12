"""Database-authorized Telegram admin panel entry and callbacks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.bot.keyboards.admin import (
    AdminApplicationCallback,
    AdminChangeCallback,
    AdminPanelCallback,
    admin_menu_keyboard,
)
from app.bot.keyboards.admin_schedule import (
    AdminScheduleCallback,
    admin_schedule_keyboard,
    admin_schedule_slots_keyboard,
)
from app.bot.keyboards.appointment_actions import (
    RejectAppointmentCallback,
    TYPICAL_REJECTION_REASONS,
    rejection_confirmation_keyboard,
    rejection_reasons_keyboard,
)
from app.core.config import Settings
from app.database.enums import AppointmentStatus
from app.database.models import (
    Appointment,
    CalculationFactor,
    CalculationFactorValue,
    ConversationState,
    FAQItem,
    ManagerRequest,
    Service,
    ServicePrice,
    User,
)
from app.database.repositories import (
    ConversationStateRepository,
    AvailableSlotRepository,
)
from app.services.admin_auth import (
    AdminAccessDenied,
    AdminAuthorizationService,
    Permission,
)
from app.services.admin_notifications import build_admin_application_text
from app.services.application_summary import ApplicationSummaryService
from app.services.admin_appointments import AdminAppointmentService
from app.services.appointment_changes import AppointmentChangeService
from app.services.client_notifications import ClientNotificationService
from app.services.content_admin import (
    ContentAdminService,
    EDITABLE_CONTENT,
    effective_reminder_hours,
)
from app.bot.keyboards.content_admin import (
    ContentAdminCallback,
    content_preview_keyboard,
    content_settings_keyboard,
)
from app.bot.keyboards.entity_admin import (
    EntityAdminCallback,
    entity_list_keyboard,
    entity_preview_keyboard,
)
from app.bot.keyboards.manager import manager_request_keyboard
from app.services.entity_admin import EntityAdminService
from app.services.admin_schedule import (
    AdminScheduleError,
    AdminScheduleService,
    parse_slot_drafts,
)
from app.services.vehicle_selection import VehicleSelectionError, clean_user_text

router = Router(name="admin")
ADMIN_REJECT_FLOW = "admin_reject"
ADMIN_CHANGE_FLOW = "admin_change"
ADMIN_SCHEDULE_FLOW = "admin_schedule"
ADMIN_SCHEDULE_STATE_TTL = timedelta(minutes=30)

SECTION_PERMISSIONS = {
    "admins": Permission.MANAGE_ADMINS,
    "roles": Permission.MANAGE_ADMINS,
    "new": Permission.VIEW_APPOINTMENTS,
    "today": Permission.VIEW_APPOINTMENTS,
    "tomorrow": Permission.VIEW_APPOINTMENTS,
    "future": Permission.VIEW_APPOINTMENTS,
    "all": Permission.VIEW_APPOINTMENTS,
    "schedule": Permission.MANAGE_SCHEDULE,
    "free_slots": Permission.MANAGE_SCHEDULE,
    "services": Permission.MANAGE_SERVICES,
    "prices": Permission.MANAGE_PRICES,
    "calculator": Permission.MANAGE_PRICES,
    "faq": Permission.MANAGE_FAQ,
    "requests": Permission.MANAGE_REQUESTS,
    "clients": Permission.VIEW_CLIENTS,
    "statistics": Permission.VIEW_STATISTICS,
    "settings": Permission.MANAGE_SETTINGS,
    "audit": Permission.VIEW_AUDIT,
}

APPLICATION_ACTION_PERMISSIONS = {
    "confirm": Permission.MANAGE_APPOINTMENTS,
    "reject": Permission.MANAGE_APPOINTMENTS,
    "reschedule": Permission.MANAGE_APPOINTMENTS,
    "write": Permission.VIEW_APPOINTMENTS,
    "open": Permission.VIEW_APPOINTMENTS,
}


@router.message(Command("admin"))
async def handle_admin(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        admin = await AdminAuthorizationService(session).require(
            message.from_user.id, Permission.DASHBOARD
        )
    except AdminAccessDenied as error:
        await message.answer(str(error))
        return
    await message.answer(
        f"Административная панель. Роль: <b>{admin.role.value}</b>",
        reply_markup=admin_menu_keyboard(),
    )


@router.callback_query(AdminPanelCallback.filter())
async def handle_admin_section(
    callback: CallbackQuery,
    callback_data: AdminPanelCallback,
    session: AsyncSession,
    app_user: User,
    settings: Settings,
) -> None:
    if callback.from_user is None:
        return
    permission = SECTION_PERMISSIONS.get(callback_data.section)
    if permission is None:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    try:
        await AdminAuthorizationService(session).require(
            callback.from_user.id, permission
        )
    except AdminAccessDenied as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        if callback_data.section == "schedule":
            await show_admin_schedule_menu(callback.message)
            return
        if callback_data.section == "free_slots":
            await show_admin_schedule_slots(callback.message, session, settings)
            return
        if callback_data.section == "settings":
            await callback.message.answer(
                "Выберите настройку:", reply_markup=content_settings_keyboard()
            )
            return
        if callback_data.section == "requests":
            requests = list(
                (
                    await session.execute(
                        select(ManagerRequest)
                        .order_by(ManagerRequest.created_at.desc())
                        .limit(50)
                    )
                ).scalars()
            )
            if not requests:
                await callback.message.answer("Обращений нет.")
            for request in requests:
                await callback.message.answer(
                    f"#{str(request.id)[:8]} · {request.topic} · {request.status.value}",
                    reply_markup=manager_request_keyboard(request.id),
                )
            return
        entity_sections = {
            "services": ("service", Service),
            "prices": ("price", ServicePrice),
            "faq": ("faq", FAQItem),
            "calculator": ("factor", CalculationFactor),
        }
        if callback_data.section in entity_sections:
            entity, model = entity_sections[callback_data.section]
            items = list(
                (
                    await session.execute(
                        select(model).order_by(model.created_at).limit(50)
                    )
                ).scalars()
            )
            await callback.message.answer(
                "Выберите запись для редактирования:" if items else "Записей нет.",
                reply_markup=entity_list_keyboard(entity, items) if items else None,
            )
            if callback_data.section == "calculator":
                values = list(
                    (
                        await session.execute(
                            select(CalculationFactorValue)
                            .order_by(CalculationFactorValue.created_at)
                            .limit(50)
                        )
                    ).scalars()
                )
                if values:
                    await callback.message.answer(
                        "Значения факторов:",
                        reply_markup=entity_list_keyboard("factor_value", values),
                    )
            return
        await callback.message.answer(
            f"Раздел <b>{callback_data.section}</b> доступен. "
            "Его операции будут подключены следующими этапами."
        )


async def show_admin_schedule_menu(message: Message) -> None:
    await message.answer(
        "<b>Расписание</b>\n\n"
        "Добавляйте доступные слоты — пользователи увидят их в календаре записи. "
        "Один слот: <code>15.07.2026 10:00 120</code>, где последнее число — "
        "длительность в минутах. Можно отправить несколько строк за раз.",
        reply_markup=admin_schedule_keyboard(),
    )


async def show_admin_schedule_slots(
    message: Message, session: AsyncSession, settings: Settings
) -> None:
    slots = await AdminScheduleService(session).list_open_slots()
    if not slots:
        await message.answer(
            "Открытых будущих слотов пока нет.",
            reply_markup=admin_schedule_keyboard(),
        )
        return
    await message.answer(
        "Ближайшие открытые слоты. Нажмите на слот, чтобы закрыть его для новых записей.",
        reply_markup=admin_schedule_slots_keyboard(slots, settings.app_timezone),
    )


@router.callback_query(AdminScheduleCallback.filter())
async def handle_admin_schedule_callback(
    callback: CallbackQuery,
    callback_data: AdminScheduleCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        return
    try:
        admin = await AdminAuthorizationService(session).require(
            callback.from_user.id, Permission.MANAGE_SCHEDULE
        )
    except AdminAccessDenied as error:
        await callback.answer(str(error), show_alert=True)
        return

    states = ConversationStateRepository(session)
    if callback_data.action == "menu":
        state = await states.get_active_for_flow(
            app_user.id, ADMIN_SCHEDULE_FLOW, datetime.now(UTC)
        )
        if state is not None:
            await session.delete(state)
        await callback.answer()
        await show_admin_schedule_menu(callback.message)
        return
    if callback_data.action == "add":
        await states.upsert(
            user_id=app_user.id,
            flow=ADMIN_SCHEDULE_FLOW,
            step="slot_input",
            payload={},
            expires_at=datetime.now(UTC) + ADMIN_SCHEDULE_STATE_TTL,
        )
        await callback.answer()
        await callback.message.answer(
            "Отправьте слоты отдельными строками в формате:\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ ДЛИТЕЛЬНОСТЬ_В_МИНУТАХ</code>\n\n"
            "Например:\n<code>15.07.2026 10:00 120\n15.07.2026 13:00 120</code>"
        )
        return
    if callback_data.action == "list":
        await callback.answer()
        await show_admin_schedule_slots(callback.message, session, settings)
        return
    if callback_data.action == "close":
        try:
            slot_id = UUID(callback_data.value)
            slot = await AdminScheduleService(session).close_slot(admin, slot_id)
            await session.commit()
        except (AdminScheduleError, ValueError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer("Слот закрыт")
        starts_at = slot.starts_at.astimezone(settings.app_timezone)
        await callback.message.answer(
            f"Слот {starts_at:%d.%m.%Y %H:%M} закрыт для новых записей."
        )
        await show_admin_schedule_slots(callback.message, session, settings)
        return
    await callback.answer("Действие устарело", show_alert=True)


class AdminScheduleInputFilter(BaseFilter):
    async def __call__(self, message: Message, app_user: User, session: AsyncSession):
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, ADMIN_SCHEDULE_FLOW, datetime.now(UTC)
        )
        return (
            {"admin_schedule_state": state}
            if state is not None and state.step == "slot_input"
            else False
        )


@router.message(F.text & ~F.text.startswith("/"), AdminScheduleInputFilter())
async def handle_admin_schedule_input(
    message: Message,
    admin_schedule_state: ConversationState,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    try:
        admin = await AdminAuthorizationService(session).require(
            message.from_user.id, Permission.MANAGE_SCHEDULE
        )
        drafts = parse_slot_drafts(
            message.text or "",
            timezone=settings.app_timezone,
            booking_days_ahead=settings.booking_days_ahead,
        )
        slots = await AdminScheduleService(session).create_slots(admin, drafts)
    except (AdminAccessDenied, AdminScheduleError) as error:
        await message.answer(str(error))
        return
    await session.delete(admin_schedule_state)
    await session.commit()
    local_slots = [slot.starts_at.astimezone(settings.app_timezone) for slot in slots]
    rendered = "\n".join(
        f"• {slot:%d.%m.%Y %H:%M}" for slot in local_slots
    )
    await message.answer(
        f"Добавлено слотов: <b>{len(slots)}</b>.\n{rendered}",
        reply_markup=admin_schedule_keyboard(),
    )


class ContentEditFilter(BaseFilter):
    async def __call__(self, message: Message, app_user: User, session: AsyncSession):
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, "content_edit", datetime.now(UTC)
        )
        return (
            {"content_edit_state": state} if state and state.step == "input" else False
        )


@router.callback_query(ContentAdminCallback.filter())
async def content_admin_callback(
    callback: CallbackQuery,
    callback_data: ContentAdminCallback,
    app_user: User,
    session: AsyncSession,
):
    try:
        admin = await AdminAuthorizationService(session).require(
            callback.from_user.id, Permission.MANAGE_SETTINGS
        )
    except AdminAccessDenied as error:
        return await callback.answer(str(error), show_alert=True)
    states = ConversationStateRepository(session)
    state = await states.get_active_for_flow(
        app_user.id, "content_edit", datetime.now(UTC)
    )
    if callback_data.action == "edit":
        await states.upsert(
            user_id=app_user.id,
            flow="content_edit",
            step="input",
            payload={"key": callback_data.key},
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        await callback.answer()
        return await callback.message.answer(
            f"Введите новое значение: {EDITABLE_CONTENT.get(callback_data.key, callback_data.key)}"
        )
    if callback_data.action == "cancel":
        if state:
            await session.delete(state)
        return await callback.answer("Редактирование отменено")
    if callback_data.action == "save":
        if (
            state is None
            or state.step != "confirm"
            or state.payload.get("key") != callback_data.key
        ):
            return await callback.answer("Предпросмотр устарел", show_alert=True)
        preview = await ContentAdminService(session).preview(
            callback_data.key, state.payload["new_value"]
        )
        if preview.old_value != state.payload.get("old_value"):
            return await callback.answer(
                "Значение уже изменилось. Повторите редактирование.", show_alert=True
            )
        await ContentAdminService(session).save(admin, preview)
        await session.delete(state)
        await session.commit()
        await callback.answer("Сохранено")
        await callback.message.answer(
            "Настройка сохранена, изменение записано в аудит."
        )


@router.message(F.text & ~F.text.startswith("/"), ContentEditFilter())
async def content_admin_input(
    message: Message,
    content_edit_state: ConversationState,
    app_user: User,
    session: AsyncSession,
):
    try:
        await AdminAuthorizationService(session).require(
            message.from_user.id, Permission.MANAGE_SETTINGS
        )
    except AdminAccessDenied as error:
        return await message.answer(str(error))
    key = content_edit_state.payload["key"]
    try:
        preview = await ContentAdminService(session).preview(key, message.text)
    except (ValueError, VehicleSelectionError) as error:
        return await message.answer(str(error))
    await ConversationStateRepository(session).upsert(
        user_id=app_user.id,
        flow="content_edit",
        step="confirm",
        payload={
            "key": key,
            "old_value": preview.old_value,
            "new_value": preview.new_value,
        },
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await message.answer(
        f"Старое значение:\n{preview.old_value or '—'}\n\nНовое значение:\n{preview.new_value}",
        reply_markup=content_preview_keyboard(key),
    )


class EntityEditFilter(BaseFilter):
    async def __call__(self, message: Message, app_user: User, session: AsyncSession):
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, "entity_edit", datetime.now(UTC)
        )
        return (
            {"entity_edit_state": state} if state and state.step == "input" else False
        )


@router.callback_query(EntityAdminCallback.filter())
async def entity_admin_callback(
    callback: CallbackQuery,
    callback_data: EntityAdminCallback,
    app_user: User,
    session: AsyncSession,
):
    permission = (
        Permission.MANAGE_FAQ
        if callback_data.entity == "faq"
        else Permission.MANAGE_SERVICES
        if callback_data.entity == "service"
        else Permission.MANAGE_PRICES
    )
    try:
        admin = await AdminAuthorizationService(session).require(
            callback.from_user.id, permission
        )
    except AdminAccessDenied as error:
        return await callback.answer(str(error), show_alert=True)
    states = ConversationStateRepository(session)
    state = await states.get_active_for_flow(
        app_user.id, "entity_edit", datetime.now(UTC)
    )
    if callback_data.action == "edit":
        await states.upsert(
            user_id=app_user.id,
            flow="entity_edit",
            step="input",
            payload={
                "entity": callback_data.entity,
                "entity_id": str(callback_data.entity_id),
            },
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        await callback.answer()
        return await callback.message.answer(
            'Введите изменяемые поля в JSON, например: {"name":"Новое название"}'
        )
    if callback_data.action == "cancel":
        if state:
            await session.delete(state)
        return await callback.answer("Редактирование отменено")
    if callback_data.action == "save":
        if state is None or state.step != "confirm":
            return await callback.answer("Предпросмотр устарел", show_alert=True)
        try:
            await EntityAdminService(session).save(
                admin,
                callback_data.entity,
                callback_data.entity_id,
                state.payload["updates"],
                state.payload["old"],
            )
        except ValueError as error:
            return await callback.answer(str(error), show_alert=True)
        await session.delete(state)
        await session.commit()
        await callback.answer("Сохранено")
        await callback.message.answer("Изменение сохранено и записано в аудит.")


@router.message(F.text & ~F.text.startswith("/"), EntityEditFilter())
async def entity_admin_input(
    message: Message,
    entity_edit_state: ConversationState,
    app_user: User,
    session: AsyncSession,
):
    try:
        updates = json.loads(message.text or "")
    except json.JSONDecodeError:
        return await message.answer("Некорректный JSON.")
    if not isinstance(updates, dict) or not updates:
        return await message.answer("Укажите хотя бы одно поле.")
    entity = entity_edit_state.payload["entity"]
    entity_id = UUID(entity_edit_state.payload["entity_id"])
    permission = (
        Permission.MANAGE_FAQ
        if entity == "faq"
        else Permission.MANAGE_SERVICES
        if entity == "service"
        else Permission.MANAGE_PRICES
    )
    try:
        await AdminAuthorizationService(session).require(
            message.from_user.id, permission
        )
        _, converted, old, new = await EntityAdminService(session).preview(
            entity, entity_id, updates
        )
    except (AdminAccessDenied, ValueError) as error:
        return await message.answer(str(error))
    serializable_updates = {
        k: (str(v) if hasattr(v, "as_tuple") else v) for k, v in converted.items()
    }
    await ConversationStateRepository(session).upsert(
        user_id=app_user.id,
        flow="entity_edit",
        step="confirm",
        payload={
            "entity": entity,
            "entity_id": str(entity_id),
            "updates": serializable_updates,
            "old": old,
            "new": new,
        },
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await message.answer(
        f"Старое значение:\n{json.dumps(old, ensure_ascii=False, indent=2)}\n\nНовое значение:\n{json.dumps(new, ensure_ascii=False, indent=2)}",
        reply_markup=entity_preview_keyboard(entity, entity_id),
    )


@router.callback_query(AdminApplicationCallback.filter())
async def handle_admin_application_action(
    callback: CallbackQuery,
    callback_data: AdminApplicationCallback,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    permission = APPLICATION_ACTION_PERMISSIONS.get(callback_data.action)
    if permission is None:
        await callback.answer("Действие не найдено", show_alert=True)
        return
    try:
        admin = await AdminAuthorizationService(session).require(
            callback.from_user.id, permission
        )
    except AdminAccessDenied as error:
        await callback.answer(str(error), show_alert=True)
        return

    if callback.message is None:
        return
    if callback_data.action == "confirm":
        try:
            result = await AdminAppointmentService(session).confirm(
                admin,
                callback_data.appointment_id,
                await effective_reminder_hours(session, settings.reminder_hours),
            )
            user = await session.get(User, result.appointment.user_id)
            await session.commit()
            delivered = True
            if user is not None:
                try:
                    await ClientNotificationService(
                        session, bot, settings
                    ).send_confirmation(result.appointment, user)
                except TelegramAPIError:
                    delivered = False
            await callback.answer("Заявка подтверждена")
            suffix = "" if delivered else " Уведомить клиента не удалось."
            await callback.message.answer(
                f"Заявка подтверждена. Создано напоминаний: {result.reminders_created}.{suffix}"
            )
        except VehicleSelectionError as error:
            await callback.answer(str(error), show_alert=True)
        return
    if callback_data.action == "reject":
        await callback.answer()
        await callback.message.answer(
            "Выберите причину отклонения:",
            reply_markup=rejection_reasons_keyboard(callback_data.appointment_id),
        )
        return
    if callback_data.action == "reschedule":
        now = datetime.now(UTC)
        app_user = await session.scalar(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        if app_user is None:
            await callback.answer(
                "Пользователь администратора не найден", show_alert=True
            )
            return
        await ConversationStateRepository(session).upsert(
            user_id=app_user.id,
            flow=ADMIN_CHANGE_FLOW,
            step="select_slot",
            payload={"appointment_id": str(callback_data.appointment_id)},
            expires_at=now + timedelta(minutes=30),
        )
        slots = await AvailableSlotRepository(session).list_available_between(
            now, now + timedelta(days=settings.booking_days_ahead + 1), now
        )
        rows = [
            [
                InlineKeyboardButton(
                    text=slot.starts_at.astimezone(settings.app_timezone).strftime(
                        "%d.%m %H:%M"
                    ),
                    callback_data=AdminChangeCallback(
                        action="slot",
                        value=str(slot.id),
                    ).pack(),
                )
            ]
            for slot in slots[:20]
        ]
        if slots:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Предложить ближайшие варианты клиенту",
                        callback_data=AdminChangeCallback(action="offer").pack(),
                    )
                ]
            )
        await callback.answer()
        await callback.message.answer(
            "Выберите новый слот:" if rows else "Свободных слотов нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        )
        return

    appointment = await session.get(Appointment, callback_data.appointment_id)
    if appointment is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await callback.answer()
    if callback_data.action == "open":
        user = await session.get(User, appointment.user_id)
        if user is None:
            await callback.message.answer("Пользователь заявки не найден.")
            return
        summary = await ApplicationSummaryService(session).for_appointment(
            appointment, user
        )
        admin_user = await session.scalar(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        if admin_user is not None:
            await ConversationStateRepository(session).upsert(
                user_id=admin_user.id,
                flow=ADMIN_CHANGE_FLOW,
                step="manage",
                payload={"appointment_id": str(appointment.id)},
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
        management = None
        if appointment.status == AppointmentStatus.CONFIRMED:
            management = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Перенести",
                            callback_data=AdminApplicationCallback(
                                action="reschedule", appointment_id=appointment.id
                            ).pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Отменить запись",
                            callback_data=AdminChangeCallback(
                                action="cancel", value="Отмена администратором"
                            ).pack(),
                        )
                    ],
                ]
            )
        await callback.message.answer(
            build_admin_application_text(summary, settings), reply_markup=management
        )
    else:
        await callback.message.answer(
            "Право подтверждено сервером. Действие "
            f"<b>{callback_data.action}</b> пока недоступно."
        )


@router.callback_query(AdminChangeCallback.filter())
async def handle_admin_change(
    callback: CallbackQuery,
    callback_data: AdminChangeCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    try:
        admin = await AdminAuthorizationService(session).require(
            callback.from_user.id, Permission.MANAGE_APPOINTMENTS
        )
    except AdminAccessDenied as error:
        await callback.answer(str(error), show_alert=True)
        return
    if callback.message is None:
        return
    service = AppointmentChangeService(
        session,
        deadline_hours=settings.appointment_change_deadline_hours,
        reservation_minutes=settings.slot_reservation_minutes,
    )
    try:
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, ADMIN_CHANGE_FLOW, datetime.now(UTC)
        )
        if state is None:
            raise VehicleSelectionError("Сценарий изменения записи истёк.")
        appointment_id = UUID(str(state.payload.get("appointment_id")))
        if callback_data.action == "slot":
            await service.reserve_new_slot(
                admin, appointment_id, UUID(callback_data.value), as_admin=True
            )
            await callback.answer()
            await callback.message.answer(
                "Новый слот временно зарезервирован.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Подтвердить перенос",
                                callback_data=AdminChangeCallback(
                                    action="confirm"
                                ).pack(),
                            )
                        ]
                    ]
                ),
            )
        elif callback_data.action == "confirm":
            appointment = await session.get(Appointment, appointment_id)
            await service.confirm_reschedule(
                admin,
                appointment_id,
                reminder_hours=await effective_reminder_hours(
                    session, settings.reminder_hours
                ),
                as_admin=True,
            )
            await session.commit()
            if appointment is not None:
                user = await session.get(User, appointment.user_id)
                if user is not None:
                    await bot.send_message(
                        user.telegram_id,
                        f"Администратор перенёс запись на {appointment.scheduled_at.astimezone(settings.app_timezone):%d.%m.%Y %H:%M}.",
                    )
            await callback.answer("Запись перенесена")
            await callback.message.answer("Запись перенесена, напоминания обновлены.")
        elif callback_data.action == "cancel":
            reason = clean_user_text(callback_data.value, min_length=2, max_length=500)
            appointment = await session.get(Appointment, appointment_id)
            await service.cancel(admin, appointment_id, reason, as_admin=True)
            await session.commit()
            if appointment is not None:
                user = await session.get(User, appointment.user_id)
                if user is not None:
                    await bot.send_message(
                        user.telegram_id,
                        f"Запись отменена администратором. Причина: {reason}",
                    )
            await callback.answer("Запись отменена")
        elif callback_data.action == "offer":
            appointment = await session.get(Appointment, appointment_id)
            if appointment is None:
                raise VehicleSelectionError("Запись не найдена.")
            user = await session.get(User, appointment.user_id)
            now = datetime.now(UTC)
            slots = await AvailableSlotRepository(session).list_available_between(
                now, now + timedelta(days=settings.booking_days_ahead + 1), now
            )
            if user is None or not slots:
                raise VehicleSelectionError("Клиент или свободные варианты не найдены.")
            variants = "\n".join(
                f"• {slot.starts_at.astimezone(settings.app_timezone):%d.%m.%Y %H:%M}"
                for slot in slots[:3]
            )
            await bot.send_message(
                user.telegram_id,
                "Администратор предлагает другие варианты времени:\n"
                f"{variants}\n\nДля выбора свяжитесь с менеджером.",
            )
            await callback.answer("Варианты отправлены")
    except (VehicleSelectionError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)


class AdminRejectInputFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        app_user: User,
        session: AsyncSession,
    ) -> bool | dict:
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, ADMIN_REJECT_FLOW, datetime.now(UTC)
        )
        if state is None or state.step != "reason_input":
            return False
        return {"admin_reject_state": state}


async def _require_manage_appointment(telegram_id: int, session: AsyncSession):
    return await AdminAuthorizationService(session).require(
        telegram_id, Permission.MANAGE_APPOINTMENTS
    )


@router.callback_query(RejectAppointmentCallback.filter())
async def handle_rejection_callback(
    callback: CallbackQuery,
    callback_data: RejectAppointmentCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    try:
        admin = await _require_manage_appointment(callback.from_user.id, session)
    except AdminAccessDenied as error:
        await callback.answer(str(error), show_alert=True)
        return
    if callback.message is None:
        return
    states = ConversationStateRepository(session)
    if callback_data.action == "preview":
        reason = TYPICAL_REJECTION_REASONS.get(callback_data.reason)
        if reason is None:
            await callback.answer("Причина не найдена", show_alert=True)
            return
        await callback.answer()
        await callback.message.answer(
            f"Причина: <b>{reason}</b>\nПодтвердите действие.",
            reply_markup=rejection_confirmation_keyboard(
                callback_data.appointment_id, callback_data.reason
            ),
        )
        return
    if callback_data.action == "custom":
        await states.upsert(
            user_id=app_user.id,
            flow=ADMIN_REJECT_FLOW,
            step="reason_input",
            payload={"appointment_id": str(callback_data.appointment_id)},
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        await callback.answer()
        await callback.message.answer("Введите причину отклонения:")
        return
    if callback_data.action == "abort":
        state = await states.get_for_flow(app_user.id, ADMIN_REJECT_FLOW)
        if state is not None:
            await session.delete(state)
        await callback.answer("Отклонение отменено")
        return
    if callback_data.action != "confirm":
        await callback.answer("Действие не найдено", show_alert=True)
        return

    if callback_data.reason == "custom":
        state = await states.get_active_for_flow(
            app_user.id, ADMIN_REJECT_FLOW, datetime.now(UTC)
        )
        if (
            state is None
            or state.step != "reason_confirm"
            or state.payload.get("appointment_id") != str(callback_data.appointment_id)
        ):
            await callback.answer("Причина устарела", show_alert=True)
            return
        reason = str(state.payload.get("reason", ""))
    else:
        reason = TYPICAL_REJECTION_REASONS.get(callback_data.reason, "")
    if not reason:
        await callback.answer("Причина не найдена", show_alert=True)
        return
    try:
        result = await AdminAppointmentService(session).reject(
            admin, callback_data.appointment_id, reason
        )
        state = await states.get_for_flow(app_user.id, ADMIN_REJECT_FLOW)
        if state is not None:
            await session.delete(state)
        user = await session.get(User, result.appointment.user_id)
        await session.commit()
        delivered = True
        if user is not None:
            try:
                await ClientNotificationService(session, bot, settings).send_rejection(
                    result.appointment, user
                )
            except TelegramAPIError:
                delivered = False
        await callback.answer("Заявка отклонена")
        suffix = "" if delivered else " Уведомить клиента не удалось."
        await callback.message.answer(
            f"Заявка отклонена. Отменено напоминаний: {result.reminders_cancelled}.{suffix}"
        )
    except VehicleSelectionError as error:
        await callback.answer(str(error), show_alert=True)


@router.message(F.text & ~F.text.startswith("/"), AdminRejectInputFilter())
async def receive_custom_rejection_reason(
    message: Message,
    admin_reject_state: ConversationState,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return
    try:
        await _require_manage_appointment(message.from_user.id, session)
        reason = clean_user_text(message.text, min_length=2, max_length=500)
    except (AdminAccessDenied, VehicleSelectionError) as error:
        await message.answer(str(error))
        return
    appointment_id = admin_reject_state.payload.get("appointment_id")
    try:
        appointment_uuid = UUID(str(appointment_id))
    except (TypeError, ValueError):
        await message.answer("Состояние отклонения повреждено.")
        return
    await ConversationStateRepository(session).upsert(
        user_id=admin_reject_state.user_id,
        flow=ADMIN_REJECT_FLOW,
        step="reason_confirm",
        payload={"appointment_id": str(appointment_uuid), "reason": reason},
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await message.answer(
        f"Причина: <b>{reason}</b>\nПодтвердите действие.",
        reply_markup=rejection_confirmation_keyboard(appointment_uuid, "custom"),
    )
