"""Calendar navigation and atomic time-slot reservation handlers."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import ScheduleCallback, main_menu_keyboard
from app.bot.keyboards.schedule import calendar_keyboard, times_keyboard
from app.core.config import Settings
from app.database.models import ConversationState, User
from app.services.schedule import ScheduleService, SlotUnavailableError
from app.services.user_entry import BOOKING_FLOW, UserEntryService
from app.services.vehicle_selection import (
    VehicleSelectionError,
    VehicleSelectionService,
)

router = Router(name="schedule")


def _service(session: AsyncSession, settings: Settings) -> ScheduleService:
    return ScheduleService(
        session,
        timezone=settings.app_timezone,
        booking_days_ahead=settings.booking_days_ahead,
        reservation_minutes=settings.slot_reservation_minutes,
    )


async def show_calendar(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
    *,
    year: int | None = None,
    month: int | None = None,
) -> None:
    local_now = datetime.now(settings.app_timezone)
    data = await _service(session, settings).calendar_month(
        user, year or local_now.year, month or local_now.month
    )
    await message.answer(
        "Выберите доступную дату. Точки недоступны для выбора:",
        reply_markup=calendar_keyboard(data),
    )


async def show_times(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
    selected_date: date,
) -> None:
    slots = await _service(session, settings).times_for_date(user, selected_date)
    text = f"Доступное время на <b>{selected_date.strftime('%d.%m.%Y')}</b>:"
    if not slots:
        text = "На выбранную дату свободного времени больше нет."
    await message.answer(
        text, reply_markup=times_keyboard(slots, settings.app_timezone)
    )


async def render_schedule_step(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
    state: ConversationState,
) -> None:
    if state.step == "date_selection":
        selected = state.payload.get("selected_date")
        if selected:
            try:
                await show_times(
                    message, user, session, settings, date.fromisoformat(str(selected))
                )
                return
            except (ValueError, VehicleSelectionError):
                pass
        await show_calendar(message, user, session, settings)
    elif state.step == "contact_name":
        from app.bot.handlers.contacts import render_contact_step

        await render_contact_step(message, user, session, settings, state)


@router.callback_query(ScheduleCallback.filter())
async def handle_schedule_callback(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    service = _service(session, settings)
    try:
        if callback_data.action == "month":
            year, month = map(int, callback_data.value.split("-"))
            await show_calendar(
                callback.message, app_user, session, settings, year=year, month=month
            )
        elif callback_data.action == "date":
            selected = date.fromisoformat(callback_data.value)
            await VehicleSelectionService(session).set_step(
                app_user,
                BOOKING_FLOW,
                "date_selection",
                selected_date=selected.isoformat(),
            )
            await show_times(callback.message, app_user, session, settings, selected)
        elif callback_data.action == "slot":
            state = await service.states.get_active_for_flow(
                app_user.id, BOOKING_FLOW, datetime.now(settings.app_timezone)
            )
            selected = state.payload.get("selected_date") if state else None
            try:
                result = await service.reserve(app_user, UUID(callback_data.value))
            except SlotUnavailableError as error:
                await callback.message.answer(str(error))
                if selected:
                    await show_times(
                        callback.message,
                        app_user,
                        session,
                        settings,
                        date.fromisoformat(str(selected)),
                    )
                else:
                    await show_calendar(callback.message, app_user, session, settings)
                return
            await render_schedule_step(
                callback.message, app_user, session, settings, result.state
            )
        elif callback_data.action == "back_calendar":
            await VehicleSelectionService(session).set_step(
                app_user, BOOKING_FLOW, "date_selection", selected_date=None
            )
            await show_calendar(callback.message, app_user, session, settings)
        elif callback_data.action in {"back_service", "back_photos"}:
            state = await VehicleSelectionService(session).set_step(
                app_user, BOOKING_FLOW, "service_selection"
            )
            from app.bot.handlers.services import render_service_step

            await render_service_step(callback.message, app_user, session, state)
        elif callback_data.action == "cancel":
            await UserEntryService(session).cancel_flow(app_user, BOOKING_FLOW)
            await callback.message.answer(
                "Сценарий отменён.", reply_markup=main_menu_keyboard()
            )
    except (VehicleSelectionError, ValueError) as error:
        await callback.message.answer(str(error), reply_markup=main_menu_keyboard())
