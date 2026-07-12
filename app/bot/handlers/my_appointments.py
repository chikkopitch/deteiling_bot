from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import MY_APPOINTMENTS
from app.bot.keyboards.my_appointments import (
    CANCEL_REASONS,
    MyAppointmentCallback,
    appointment_actions_keyboard,
    appointments_keyboard,
    cancellation_keyboard,
    categories_keyboard,
    dates_keyboard,
    reschedule_confirmation_keyboard,
    slots_keyboard,
)
from app.bot.keyboards.appointment_actions import UserAppointmentCallback
from app.core.config import Settings
from app.database.enums import AppointmentStatus
from app.database.models import User
from app.database.repositories import (
    AdminRepository,
    AppointmentRepository,
    AvailableSlotRepository,
)
from app.services.application_summary import ApplicationSummaryService
from app.services.appointment_changes import AppointmentChangeService
from app.services.schedule import SlotUnavailableError
from app.services.vehicle_selection import VehicleSelectionError
from app.services.content_admin import effective_reminder_hours

router = Router(name="my_appointments")

GROUPS = {
    "active": (AppointmentStatus.WAITING_ADMIN, AppointmentStatus.CONFIRMED),
    "completed": (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW),
    "cancelled": (
        AppointmentStatus.REJECTED,
        AppointmentStatus.CANCELLED_BY_USER,
        AppointmentStatus.CANCELLED_BY_ADMIN,
    ),
}


def _changes(session, settings):
    return AppointmentChangeService(
        session,
        deadline_hours=settings.appointment_change_deadline_hours,
        reservation_minutes=settings.slot_reservation_minutes,
    )


async def _notify_admins(session: AsyncSession, bot: Bot, text: str) -> None:
    for admin in await AdminRepository(session).list_active():
        try:
            await bot.send_message(admin.telegram_id, text)
        except Exception:
            # Delivery failure must not roll back an already committed appointment change.
            continue


async def show_root(message: Message) -> None:
    await message.answer("Мои записи", reply_markup=categories_keyboard())


@router.message(F.text == MY_APPOINTMENTS)
async def my_appointments(message: Message) -> None:
    await show_root(message)


@router.callback_query(MyAppointmentCallback.filter())
async def handle_my_appointment(
    callback: CallbackQuery,
    callback_data: MyAppointmentCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    action = callback_data.action
    appointment_id = callback_data.appointment_id
    repo = AppointmentRepository(session)
    try:
        if action == "root":
            await show_root(callback.message)
            return
        if action == "list":
            statuses = GROUPS.get(callback_data.value)
            if statuses is None:
                raise VehicleSelectionError("Раздел не найден.")
            items = await repo.list_for_user(app_user.id, statuses)
            await callback.message.answer(
                "Записи не найдены." if not items else "Выберите запись:",
                reply_markup=appointments_keyboard(items),
            )
            return
        if appointment_id is None:
            raise VehicleSelectionError("Запись не указана.")
        appointment = await session.get(repo.model, appointment_id)
        if appointment is None or appointment.user_id != app_user.id:
            raise VehicleSelectionError("Запись не найдена.")
        if action == "open":
            summary = await ApplicationSummaryService(session).for_appointment(
                appointment, app_user
            )
            local = summary.slot.starts_at.astimezone(settings.app_timezone)
            await callback.message.answer(
                f"<b>{summary.service_name}</b>\nАвтомобиль: {summary.vehicle}\n"
                f"Статус: {appointment.status.value}\nДата: {local:%d.%m.%Y}\nВремя: {local:%H:%M}",
                reply_markup=appointment_actions_keyboard(appointment.id),
            )
        elif action == "reschedule":
            _changes(session, settings)._check_change_allowed(
                appointment, datetime.now(UTC), bypass_deadline=False
            )
            now = datetime.now(UTC)
            slots = await AvailableSlotRepository(session).list_available_between(
                now, now + timedelta(days=settings.booking_days_ahead + 1), now
            )
            dates = sorted(
                {
                    slot.starts_at.astimezone(settings.app_timezone).date()
                    for slot in slots
                }
            )
            await callback.message.answer(
                "Выберите новую дату:",
                reply_markup=dates_keyboard(appointment.id, dates),
            )
        elif action == "date":
            selected = date.fromisoformat(callback_data.value)
            local_from = datetime.combine(
                selected, time.min, settings.app_timezone
            ).astimezone(UTC)
            slots = await AvailableSlotRepository(session).list_available_between(
                local_from, local_from + timedelta(days=1), datetime.now(UTC)
            )
            await callback.message.answer(
                "Выберите новое время:",
                reply_markup=slots_keyboard(
                    appointment.id, slots, settings.app_timezone
                ),
            )
        elif action == "slot":
            reservation = await _changes(session, settings).reserve_new_slot(
                app_user, appointment.id, UUID(callback_data.value)
            )
            await callback.message.answer(
                f"Новое время временно зарезервировано до {reservation.reserved_until.astimezone(settings.app_timezone):%H:%M}.",
                reply_markup=reschedule_confirmation_keyboard(appointment.id),
            )
        elif action == "rc":
            old_time = appointment.scheduled_at
            await _changes(session, settings).confirm_reschedule(
                app_user,
                appointment.id,
                reminder_hours=await effective_reminder_hours(
                    session, settings.reminder_hours
                ),
            )
            new_time = appointment.scheduled_at
            await session.commit()
            await _notify_admins(
                session,
                bot,
                f"Клиент перенёс запись #{str(appointment.id)[:8]}: {old_time} → {new_time}",
            )
            await callback.message.answer(
                "Запись успешно перенесена.", reply_markup=categories_keyboard()
            )
        elif action == "cancel":
            _changes(session, settings)._check_change_allowed(
                appointment, datetime.now(UTC), bypass_deadline=False
            )
            await callback.message.answer(
                "Выберите причину отмены:",
                reply_markup=cancellation_keyboard(appointment.id),
            )
        elif action == "cc":
            reason = CANCEL_REASONS.get(callback_data.value)
            if reason is None:
                raise VehicleSelectionError("Причина не найдена.")
            await _changes(session, settings).cancel(app_user, appointment.id, reason)
            await session.commit()
            await _notify_admins(
                session,
                bot,
                f"Клиент отменил запись #{str(appointment.id)[:8]}. Причина: {reason}",
            )
            await callback.message.answer(
                "Запись отменена.", reply_markup=categories_keyboard()
            )
        elif action == "manager":
            await callback.message.answer(
                "Откройте раздел «Связаться с менеджером» в главном меню."
            )
    except (VehicleSelectionError, SlotUnavailableError, ValueError) as error:
        await callback.message.answer(str(error))


@router.callback_query(UserAppointmentCallback.filter())
async def handle_notification_appointment_action(
    callback: CallbackQuery,
    callback_data: UserAppointmentCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    mapping = {"reschedule": "reschedule", "cancel": "cancel", "manager": "manager"}
    action = mapping.get(callback_data.action)
    if action is None:
        await callback.answer("Действие пока недоступно", show_alert=True)
        return
    translated = MyAppointmentCallback(
        action=action, appointment_id=callback_data.appointment_id
    )
    await handle_my_appointment(callback, translated, app_user, session, settings, bot)
