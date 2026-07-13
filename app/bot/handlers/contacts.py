"""Name, Russian phone, and appointment review handlers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from aiogram import Bot, F, Router, html
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import ConversationStepFilter
from app.bot.keyboards import ContactCallback, ReviewCallback, main_menu_keyboard
from app.bot.keyboards.contacts import (
    MANUAL_PHONE_TEXT,
    name_keyboard,
    phone_navigation_keyboard,
    phone_reply_keyboard,
    review_keyboard,
)
from app.core.config import Settings
from app.database.models import Appointment, ConversationState, User
from app.services.application_summary import ApplicationSummaryService
from app.services.contacts import ContactService
from app.services.user_entry import BOOKING_FLOW, UserEntryService
from app.services.submission import SubmissionService, SubmissionStatus
from app.services.vehicle_selection import (
    VehicleSelectionError,
    VehicleSelectionService,
)

router = Router(name="contacts")


def _money(value: Decimal | None, settings: Settings) -> str:
    if value is None:
        return "не рассчитана"
    return (
        f"{value:,.2f}".replace(",", " ").replace(".00", "")
        + f" {settings.currency_symbol}"
    )


async def show_name_prompt(
    message: Message,
    user: User,
    session: AsyncSession,
    state: ConversationState | None = None,
    settings: Settings | None = None,
) -> None:
    suggested = await ContactService(session).suggested_name(user)
    name_text = (
        f"Подтвердите имя: <b>{html.quote(suggested)}</b>"
        if suggested
        else "Введите ваше имя:"
    )
    text = name_text
    if state is not None and settings is not None and state.payload.get("scheduled_at"):
        starts_at = datetime.fromisoformat(str(state.payload["scheduled_at"]))
        text = (
            "Время временно зарезервировано: "
            f"<b>{starts_at.astimezone(settings.app_timezone).strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            + name_text
        )
    await message.answer(text, reply_markup=name_keyboard(bool(suggested)))


async def show_phone_prompt(message: Message) -> None:
    await message.answer(
        "Отправьте свой контакт Telegram или введите российский номер вручную.",
        reply_markup=phone_reply_keyboard(),
    )
    await message.answer("Навигация:", reply_markup=phone_navigation_keyboard())


async def show_review(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    summary = await ApplicationSummaryService(session).for_draft(user)
    appointment = summary.appointment
    if summary.price_from == summary.price_to:
        price = _money(summary.price_from, settings)
    else:
        price = f"от {_money(summary.price_from, settings)} до {_money(summary.price_to, settings)}"
    local_time = summary.slot.starts_at.astimezone(settings.app_timezone)
    comment = appointment.vehicle_comment or "нет"
    await message.answer(
        "<b>Проверьте заявку</b>\n\n"
        f"Автомобиль: {html.quote(summary.vehicle)}\n"
        f"Услуга: {html.quote(summary.service_name)}\n"
        f"Дата: {local_time.strftime('%d.%m.%Y')}\n"
        f"Время: {local_time.strftime('%H:%M')}\n"
        f"Имя: {html.quote(appointment.customer_name or '')}\n"
        f"Телефон: {html.quote(appointment.customer_phone or '')}\n"
        f"Предварительная цена: {price}\n"
        f"Комментарий: {html.quote(comment)}",
        reply_markup=review_keyboard(),
    )


async def render_contact_step(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
    state: ConversationState,
) -> None:
    if state.step == "contact_name":
        await show_name_prompt(message, user, session, state, settings)
    elif state.step == "contact_name_input":
        await message.answer("Введите другое имя:", reply_markup=name_keyboard(False))
    elif state.step == "contact_phone":
        await show_phone_prompt(message)
    elif state.step == "contact_phone_input":
        await message.answer(
            "Введите номер, например +79991234567:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer("Навигация:", reply_markup=phone_navigation_keyboard())
    elif state.step == "review":
        await show_review(message, user, session, settings)


@router.callback_query(ContactCallback.filter())
async def handle_contact_callback(
    callback: CallbackQuery,
    callback_data: ContactCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    service = ContactService(session)
    try:
        if callback_data.action == "confirm_name":
            suggested = await service.suggested_name(app_user)
            if not suggested:
                raise VehicleSelectionError("Введите имя вручную.")
            state = await service.save_name(app_user, suggested)
            await render_contact_step(
                callback.message, app_user, session, settings, state
            )
        elif callback_data.action == "other_name":
            await service.set_step(app_user, "contact_name_input")
            await callback.message.answer("Введите другое имя:")
        elif callback_data.action == "back_name":
            state = await service.set_step(app_user, "contact_name")
            await render_contact_step(
                callback.message, app_user, session, settings, state
            )
        elif callback_data.action == "back_time":
            state = await VehicleSelectionService(session).set_step(
                app_user, BOOKING_FLOW, "date_selection"
            )
            from app.bot.handlers.schedule import render_schedule_step

            await render_schedule_step(
                callback.message, app_user, session, settings, state
            )
        elif callback_data.action == "cancel":
            await UserEntryService(session).cancel_flow(app_user, BOOKING_FLOW)
            await callback.message.answer(
                "Заполнение отменено.", reply_markup=main_menu_keyboard()
            )
    except VehicleSelectionError as error:
        await callback.message.answer(str(error))


@router.message(F.text, ConversationStepFilter("contact_name_input"))
async def receive_name(
    message: Message,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    try:
        state = await ContactService(session).save_name(app_user, message.text)
        await render_contact_step(message, app_user, session, settings, state)
    except VehicleSelectionError as error:
        await message.answer(str(error))


@router.message(F.text == MANUAL_PHONE_TEXT, ConversationStepFilter("contact_phone"))
async def request_manual_phone(
    message: Message, app_user: User, session: AsyncSession
) -> None:
    await ContactService(session).set_step(app_user, "contact_phone_input")
    await message.answer(
        "Введите номер, например +79991234567:", reply_markup=ReplyKeyboardRemove()
    )


@router.message(
    F.contact, ConversationStepFilter("contact_phone", "contact_phone_input")
)
async def receive_contact(
    message: Message,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    contact = message.contact
    if (
        contact.user_id is not None
        and message.from_user is not None
        and contact.user_id != message.from_user.id
    ):
        await message.answer(
            "Отправьте собственный контакт, а не контакт другого пользователя."
        )
        return
    try:
        state = await ContactService(session).save_phone(app_user, contact.phone_number)
        await message.answer("Телефон сохранён.", reply_markup=ReplyKeyboardRemove())
        await render_contact_step(message, app_user, session, settings, state)
    except VehicleSelectionError as error:
        await message.answer(str(error))


@router.message(F.text, ConversationStepFilter("contact_phone_input"))
async def receive_manual_phone(
    message: Message,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    try:
        state = await ContactService(session).save_phone(app_user, message.text)
        await render_contact_step(message, app_user, session, settings, state)
    except VehicleSelectionError as error:
        await message.answer(str(error))


@router.callback_query(ReviewCallback.filter())
async def handle_review_callback(
    callback: CallbackQuery,
    callback_data: ReviewCallback,
    app_user: User,
    session: AsyncSession,
    settings: Settings,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        if callback_data.action == "submit":
            result = await SubmissionService(session).submit(app_user)
            if result.status == SubmissionStatus.RESERVATION_EXPIRED:
                await session.commit()
                await callback.message.answer(
                    "Временный резерв истёк. Все заполненные данные сохранены; выберите новое время."
                )
                from app.bot.handlers.schedule import render_schedule_step

                await render_schedule_step(
                    callback.message, app_user, session, settings, result.state
                )
                return
            appointment = await session.get(Appointment, result.appointment_id)
            await session.commit()
            from app.services.admin_notifications import AdminNotificationService

            if appointment is not None:
                await AdminNotificationService(
                    session, bot, settings
                ).notify_new_application(appointment, app_user)
            await callback.message.answer(
                "Заявка отправлена и ожидает подтверждения администратора.",
                reply_markup=main_menu_keyboard(),
            )
        elif callback_data.action == "vehicle":
            state = await VehicleSelectionService(session).set_step(
                app_user, BOOKING_FLOW, "vehicle_input"
            )
            from app.bot.handlers.vehicle import render_vehicle_step

            await render_vehicle_step(callback.message, app_user, session, state)
        elif callback_data.action == "service":
            state = await VehicleSelectionService(session).set_step(
                app_user, BOOKING_FLOW, "service_selection"
            )
            from app.bot.handlers.services import render_service_step

            await render_service_step(callback.message, app_user, session, state)
        elif callback_data.action == "time":
            state = await VehicleSelectionService(session).set_step(
                app_user, BOOKING_FLOW, "date_selection", selected_date=None
            )
            from app.bot.handlers.schedule import render_schedule_step

            await render_schedule_step(
                callback.message, app_user, session, settings, state
            )
        elif callback_data.action == "contacts":
            state = await ContactService(session).set_step(app_user, "contact_name")
            await render_contact_step(
                callback.message, app_user, session, settings, state
            )
        elif callback_data.action == "cancel":
            await UserEntryService(session).cancel_flow(app_user, BOOKING_FLOW)
            await callback.message.answer(
                "Заполнение отменено.", reply_markup=main_menu_keyboard()
            )
    except VehicleSelectionError as error:
        await callback.message.answer(str(error), reply_markup=main_menu_keyboard())
