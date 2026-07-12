from datetime import timedelta
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.filters import IsAdmin
from app.bot.keyboards.callbacks import AdminCallback, BookingCallback, MenuCallback
from app.bot.states import AdminStates
from app.config import Settings
from app.models import (
    AuditLog,
    Booking,
    BookingPhoto,
    BookingStatus,
    FAQItem,
    ManagerRequest,
    ManagerRequestStatus,
    Service,
    SlotStatus,
    TimeSlot,
    User,
)
from app.services import BookingService
from app.services.errors import InvalidTransitionError, SlotUnavailableError
from app.utils.datetime import format_studio_time, utc_now

router = Router(name="admin")
PAGE_SIZE = 8


def setup(settings: Settings) -> None:
    router.message.filter(IsAdmin(settings.ADMIN_IDS))
    router.callback_query.filter(IsAdmin(settings.ADMIN_IDS))


def admin_menu() -> InlineKeyboardMarkup:
    entries = [
        ("Новые заявки", "pending"),
        ("Подтверждённые", "confirmed"),
        ("Сегодня", "today"),
        ("На этой неделе", "week"),
        ("Отменённые", "cancelled"),
        ("Расписание", "schedule"),
        ("Услуги", "services"),
        ("FAQ", "faq"),
        ("Настройки", "settings"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text, callback_data=AdminCallback(action="list", value=f"{scope}:0").pack()
                )
            ]
            for text, scope in entries
        ]
    )


def admin_card_keyboard(booking_id: UUID, owner: User) -> InlineKeyboardMarkup:
    entity_id = str(booking_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data=AdminCallback(action="confirm", entity_id=entity_id).pack(),
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=AdminCallback(action="reject", entity_id=entity_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Предложить другое время",
                    callback_data=AdminCallback(action="propose", entity_id=entity_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Написать клиенту", url=f"tg://user?id={owner.telegram_id}"
                ),
                InlineKeyboardButton(text="Позвонить", url=f"tel:{owner.phone or ''}"),
            ],
            [
                InlineKeyboardButton(
                    text="Открыть профиль", url=f"tg://user?id={owner.telegram_id}"
                ),
                InlineKeyboardButton(
                    text="История",
                    callback_data=AdminCallback(action="history", entity_id=entity_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
                )
            ],
        ]
    )


async def get_booking(session: AsyncSession, booking_id: UUID) -> Booking | None:
    return await session.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.services),
            selectinload(Booking.vehicle),
            selectinload(Booking.slot),
        )
    )


async def card_text(
    session: AsyncSession, booking: Booking, settings: Settings
) -> tuple[str, User | None]:
    owner = await session.get(User, booking.user_id)
    profile = f"@{owner.username}" if owner and owner.username else "профиль без username"
    services = ", ".join(item.name for item in booking.services) or "не выбраны"
    slot = (
        format_studio_time(booking.slot.starts_at, settings.STUDIO_TIMEZONE)
        if booking.slot
        else "не выбран"
    )
    estimate = "не рассчитывалась"
    if booking.estimated_min is not None and booking.estimated_max is not None:
        estimate = f"{booking.estimated_min:.0f}–{booking.estimated_max:.0f} ₽"
    return (
        f"Заявка #{str(booking.id)[:8]}\n"
        f"Статус: {booking.status.value}\n"
        f"Клиент: {booking.customer_name} ({profile})\n"
        f"Телефон: {booking.customer_phone}\n"
        f"Автомобиль: {booking.vehicle.brand_name} {booking.vehicle.model_name}, {booking.vehicle.year}\n"
        f"Класс: {booking.vehicle.vehicle_class}\n"
        f"Услуги: {services}\n"
        f"Предварительно: {estimate}\n"
        f"Дата и время: {slot}\n"
        f"Адрес: {settings.STUDIO_ADDRESS}\n"
        f"Комментарий: {booking.comment or '—'}\n"
        f"Создано: {format_studio_time(booking.created_at, settings.STUDIO_TIMEZONE)}",
        owner,
    )


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    await message.answer("Админ-панель", reply_markup=admin_menu())


@router.callback_query(AdminCallback.filter(F.action == "menu"))
async def menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Админ-панель", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "manager_reply"))
async def manager_reply_start(
    callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext
) -> None:
    await state.update_data(manager_request_id=callback_data.entity_id)
    await state.set_state(AdminStates.reply)
    if callback.message:
        await callback.message.edit_text("Напишите ответ клиенту:")
    await callback.answer()


@router.message(AdminStates.reply)
async def manager_reply_preview(message: Message, state: FSMContext) -> None:
    response = " ".join((message.text or "").split())
    if not 1 <= len(response) <= 2000:
        await message.answer("Ответ должен быть от 1 до 2000 символов.")
        return
    await state.update_data(manager_response=response)
    await message.answer(
        "Предпросмотр ответа:\n\n" + response,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Отправить",
                        callback_data=AdminCallback(action="manager_reply_send").pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Изменить",
                        callback_data=AdminCallback(action="manager_reply_edit").pack(),
                    )
                ],
            ]
        ),
    )


@router.callback_query(AdminStates.reply, AdminCallback.filter(F.action == "manager_reply_edit"))
async def manager_reply_edit(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text("Напишите новую версию ответа:")
    await callback.answer()


@router.callback_query(AdminStates.reply, AdminCallback.filter(F.action == "manager_reply_send"))
async def manager_reply_send(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    data = await state.get_data()
    request = await session.get(ManagerRequest, UUID(data["manager_request_id"]))
    if request is None or request.status == ManagerRequestStatus.CLOSED:
        await callback.answer("Обращение закрыто или не найдено.", show_alert=True)
        return
    request.response, request.status = data["manager_response"], ManagerRequestStatus.ANSWERED
    session.add(
        AuditLog(
            actor_user_id=db_user.id,
            action="manager_request.answered",
            entity_type="manager_request",
            entity_id=request.id,
            details={},
        )
    )
    await session.commit()
    client = await session.get(User, request.user_id)
    if client:
        await callback.bot.send_message(client.telegram_id, data["manager_response"])
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Ответ отправлен.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "manager_close"))
async def manager_close(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession, db_user: User
) -> None:
    request = await session.get(ManagerRequest, UUID(callback_data.entity_id))
    if request is None:
        await callback.answer("Обращение не найдено.", show_alert=True)
        return
    if request.status != ManagerRequestStatus.CLOSED:
        request.status = ManagerRequestStatus.CLOSED
        session.add(
            AuditLog(
                actor_user_id=db_user.id,
                action="manager_request.closed",
                entity_type="manager_request",
                entity_id=request.id,
                details={},
            )
        )
        await session.commit()
    if callback.message:
        await callback.message.edit_text("Обращение закрыто.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "service_manage"))
async def service_manage(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession
) -> None:
    item = await session.get(Service, UUID(callback_data.entity_id))
    if item is None:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    text = f"{item.name}\nЦена от: {item.price_from} ₽\nДлительность: {item.duration_minutes} мин.\nАктивна: {'да' if item.is_active else 'нет'}"
    rows = [
        [
            InlineKeyboardButton(
                text="Включить/выключить",
                callback_data=AdminCallback(action="service_toggle", entity_id=str(item.id)).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="Удалить",
                callback_data=AdminCallback(action="service_delete", entity_id=str(item.id)).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
            )
        ],
    ]
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action.in_({"service_toggle", "service_delete"})))
async def service_mutate(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession, db_user: User
) -> None:
    item = await session.get(Service, UUID(callback_data.entity_id))
    if item is None:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    if callback_data.action == "service_toggle":
        item.is_active = not item.is_active
        action = "service.toggled"
    else:
        item.is_active, item.deleted_at, action = False, utc_now(), "service.soft_deleted"
    session.add(
        AuditLog(
            actor_user_id=db_user.id,
            action=action,
            entity_type="service",
            entity_id=item.id,
            details={},
        )
    )
    await session.commit()
    if callback.message:
        await callback.message.edit_text("Изменение сохранено.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "faq_manage"))
async def faq_manage(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession
) -> None:
    item = await session.get(FAQItem, UUID(callback_data.entity_id))
    if item is None:
        await callback.answer("FAQ не найден.", show_alert=True)
        return
    rows = [
        [
            InlineKeyboardButton(
                text="Включить/выключить",
                callback_data=AdminCallback(action="faq_toggle", entity_id=str(item.id)).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="Удалить",
                callback_data=AdminCallback(action="faq_delete", entity_id=str(item.id)).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
            )
        ],
    ]
    if callback.message:
        await callback.message.edit_text(
            f"{item.question}\n\n{item.answer}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action.in_({"faq_toggle", "faq_delete"})))
async def faq_mutate(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession, db_user: User
) -> None:
    item = await session.get(FAQItem, UUID(callback_data.entity_id))
    if item is None:
        await callback.answer("FAQ не найден.", show_alert=True)
        return
    if callback_data.action == "faq_toggle":
        item.is_active = not item.is_active
        action = "faq.toggled"
    else:
        item.is_active, item.deleted_at, action = False, utc_now(), "faq.soft_deleted"
    session.add(
        AuditLog(
            actor_user_id=db_user.id,
            action=action,
            entity_type="faq",
            entity_id=item.id,
            details={},
        )
    )
    await session.commit()
    if callback.message:
        await callback.message.edit_text("Изменение сохранено.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "slot_manage"))
async def slot_manage(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession
) -> None:
    slot = await session.get(TimeSlot, UUID(callback_data.entity_id))
    if slot is None:
        await callback.answer("Слот не найден.", show_alert=True)
        return
    if slot.status == SlotStatus.BOOKED:
        await callback.answer(
            "Подтверждённый слот нельзя блокировать автоматически.", show_alert=True
        )
        return
    slot.status = SlotStatus.BLOCKED if slot.status != SlotStatus.BLOCKED else SlotStatus.AVAILABLE
    await session.commit()
    if callback.message:
        await callback.message.edit_text(
            f"Статус слота: {slot.status.value}", reply_markup=admin_menu()
        )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "list"))
async def list_bookings(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession
) -> None:
    try:
        scope, raw_page = callback_data.value.split(":", 1)
        page = max(0, int(raw_page))
    except ValueError:
        await callback.answer("Фильтр устарел.", show_alert=True)
        return
    statement = (
        select(Booking).options(selectinload(Booking.slot)).order_by(Booking.created_at.desc())
    )
    now = utc_now()
    if scope == "pending":
        statement = statement.where(Booking.status == BookingStatus.PENDING)
    elif scope == "confirmed":
        statement = statement.where(Booking.status == BookingStatus.CONFIRMED)
    elif scope == "cancelled":
        statement = statement.where(
            Booking.status.in_(
                (BookingStatus.CANCELLED_BY_CLIENT, BookingStatus.CANCELLED_BY_ADMIN)
            )
        )
    elif scope in {"today", "week"}:
        end = now + (timedelta(days=1) if scope == "today" else timedelta(days=7))
        statement = statement.join(TimeSlot).where(
            TimeSlot.starts_at >= now, TimeSlot.starts_at < end
        )
    elif scope == "services":
        service_items = list(
            await session.scalars(select(Service).order_by(Service.sort_order).limit(20))
        )
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{'✅' if item.is_active else '⛔'} {item.name}",
                    callback_data=AdminCallback(
                        action="service_manage", entity_id=str(item.id)
                    ).pack(),
                )
            ]
            for item in service_items
        ]
        rows.append(
            [
                InlineKeyboardButton(
                    text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
                )
            ]
        )
        if callback.message:
            await callback.message.edit_text(
                "Услуги: выберите элемент для управления.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        await callback.answer()
        return
    elif scope == "faq":
        faq_items = list(
            await session.scalars(
                select(FAQItem)
                .where(FAQItem.deleted_at.is_(None))
                .order_by(FAQItem.sort_order)
                .limit(20)
            )
        )
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{'✅' if item.is_active else '⛔'} {item.question}",
                    callback_data=AdminCallback(action="faq_manage", entity_id=str(item.id)).pack(),
                )
            ]
            for item in faq_items
        ]
        rows.append(
            [
                InlineKeyboardButton(
                    text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
                )
            ]
        )
        if callback.message:
            await callback.message.edit_text(
                "FAQ: выберите элемент для управления.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        await callback.answer()
        return
    elif scope == "schedule":
        slot_items = list(
            await session.scalars(
                select(TimeSlot)
                .where(TimeSlot.starts_at > utc_now())
                .order_by(TimeSlot.starts_at)
                .limit(20)
            )
        )
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{format_studio_time(item.starts_at, 'UTC')} · {item.status.value}",
                    callback_data=AdminCallback(
                        action="slot_manage", entity_id=str(item.id)
                    ).pack(),
                )
            ]
            for item in slot_items
        ]
        rows.append(
            [
                InlineKeyboardButton(
                    text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
                )
            ]
        )
        if callback.message:
            await callback.message.edit_text(
                "Ближайшие слоты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
            )
        await callback.answer()
        return
    elif scope == "settings":
        if callback.message:
            await callback.message.edit_text(
                "Настройки студии задаются переменными окружения. Изменение не затрагивает подтверждённые записи.",
                reply_markup=admin_menu(),
            )
        await callback.answer()
        return
    else:
        await callback.answer("Фильтр не найден.", show_alert=True)
        return
    booking_items = list(
        await session.scalars(statement.limit(PAGE_SIZE + 1).offset(page * PAGE_SIZE))
    )
    visible, has_next = booking_items[:PAGE_SIZE], len(booking_items) > PAGE_SIZE
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{str(item.id)[:8]} · {item.customer_name}",
                callback_data=AdminCallback(action="view", entity_id=str(item.id)).pack(),
            )
        ]
        for item in visible
    ]
    pager: list[InlineKeyboardButton] = []
    if page:
        pager.append(
            InlineKeyboardButton(
                text="←",
                callback_data=AdminCallback(action="list", value=f"{scope}:{page - 1}").pack(),
            )
        )
    if has_next:
        pager.append(
            InlineKeyboardButton(
                text="→",
                callback_data=AdminCallback(action="list", value=f"{scope}:{page + 1}").pack(),
            )
        )
    if pager:
        rows.append(pager)
    rows.append(
        [
            InlineKeyboardButton(
                text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
            )
        ]
    )
    if callback.message:
        await callback.message.edit_text(
            "Заявки:" if visible else "Заявок нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "view"))
async def view(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession, settings: Settings
) -> None:
    booking = await get_booking(session, UUID(callback_data.entity_id))
    if booking is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    text, owner = await card_text(session, booking, settings)
    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=admin_card_keyboard(
                booking.id, owner or User(telegram_id=0, first_name="Клиент")
            ),
        )
    photos = list(
        await session.scalars(
            select(BookingPhoto)
            .where(BookingPhoto.booking_id == booking.id)
            .order_by(BookingPhoto.sort_order)
        )
    )
    for photo in photos:
        await callback.bot.send_photo(callback.from_user.id, photo.file_id)
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "confirm"))
async def confirm(
    callback: CallbackQuery,
    callback_data: AdminCallback,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    booking = await BookingService(session).confirm(
        UUID(callback_data.entity_id), db_user.id, settings.REMINDER_HOURS_BEFORE
    )
    owner = await session.get(User, booking.user_id)
    if owner and booking.slot:
        services = ", ".join(item.name for item in booking.services)
        await callback.bot.send_message(
            owner.telegram_id,
            f"Запись подтверждена.\n{format_studio_time(booking.slot.starts_at, settings.STUDIO_TIMEZONE)}\n{settings.STUDIO_ADDRESS}\nУслуги: {services}\nТелефон: {settings.SUPPORT_PHONE}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Моя запись",
                            callback_data=MenuCallback(section="my_booking").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Перенести",
                            callback_data=BookingCallback(action="reschedule").pack(),
                        ),
                        InlineKeyboardButton(
                            text="Отменить",
                            callback_data=BookingCallback(action="cancel_booking").pack(),
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="Связаться с менеджером",
                            callback_data=MenuCallback(section="manager").pack(),
                        )
                    ],
                ]
            ),
        )
    if callback.message:
        await callback.message.edit_text("Запись подтверждена.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "reject"))
async def reject(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    booking_id = callback_data.entity_id
    buttons = [
        [
            InlineKeyboardButton(
                text="Время недоступно",
                callback_data=AdminCallback(
                    action="reject_reason", entity_id=booking_id, value="time"
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="Услуга недоступна",
                callback_data=AdminCallback(
                    action="reject_reason", entity_id=booking_id, value="service"
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="Не удалось связаться",
                callback_data=AdminCallback(
                    action="reject_reason", entity_id=booking_id, value="contact"
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="Другая причина",
                callback_data=AdminCallback(
                    action="reject_reason", entity_id=booking_id, value="other"
                ).pack(),
            )
        ],
    ]
    if callback.message:
        await callback.message.edit_text(
            "Выберите причину отклонения:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "reject_reason"))
async def reject_reason(
    callback: CallbackQuery,
    callback_data: AdminCallback,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    reasons = {
        "time": "Время недоступно",
        "service": "Услуга временно недоступна",
        "contact": "Не удалось связаться",
    }
    if callback_data.value == "other":
        await state.update_data(admin_reject_booking_id=callback_data.entity_id)
        await state.set_state(AdminStates.rejection_reason)
        if callback.message:
            await callback.message.edit_text("Напишите причину для внутреннего журнала:")
        await callback.answer()
        return
    booking = await BookingService(session).change_status(
        UUID(callback_data.entity_id),
        BookingStatus.CANCELLED_BY_ADMIN,
        db_user.id,
        reasons[callback_data.value],
    )
    owner = await session.get(User, booking.user_id)
    if owner:
        await callback.bot.send_message(
            owner.telegram_id,
            "К сожалению, сейчас не можем подтвердить запись. Выберите другое время или свяжитесь с менеджером.",
        )
    if callback.message:
        await callback.message.edit_text("Заявка отклонена.", reply_markup=admin_menu())
    await callback.answer()


@router.message(AdminStates.rejection_reason)
async def reject_other(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    reason = (message.text or "").strip()
    data = await state.get_data()
    booking_id = data.get("admin_reject_booking_id")
    if not reason or not booking_id:
        await message.answer("Укажите причину отклонения.")
        return
    booking = await BookingService(session).change_status(
        UUID(booking_id), BookingStatus.CANCELLED_BY_ADMIN, db_user.id, reason
    )
    owner = await session.get(User, booking.user_id)
    if owner:
        await message.bot.send_message(
            owner.telegram_id,
            "К сожалению, сейчас не можем подтвердить запись. Выберите другое время или свяжитесь с менеджером.",
        )
    await state.clear()
    await message.answer("Заявка отклонена.", reply_markup=admin_menu())


@router.callback_query(AdminCallback.filter(F.action == "history"))
async def history(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession
) -> None:
    rows = list(
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "booking",
                AuditLog.entity_id == UUID(callback_data.entity_id),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
    )
    text = (
        "\n".join(f"{item.created_at:%d.%m %H:%M} — {item.action}" for item in rows)
        or "История пока пуста."
    )
    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
                        )
                    ]
                ]
            ),
        )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "propose"))
async def propose(
    callback: CallbackQuery,
    callback_data: AdminCallback,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    slots = list(
        await session.scalars(
            select(TimeSlot)
            .where(TimeSlot.status == SlotStatus.AVAILABLE, TimeSlot.starts_at > utc_now())
            .order_by(TimeSlot.starts_at)
            .limit(12)
        )
    )
    await state.update_data(admin_reschedule_booking_id=callback_data.entity_id)
    await state.set_state(AdminStates.reschedule_slot)
    buttons = [
        [
            InlineKeyboardButton(
                text=format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE),
                callback_data=AdminCallback(action="offer_slot", entity_id=str(slot.id)).pack(),
            )
        ]
        for slot in slots
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="← Админ-меню", callback_data=AdminCallback(action="menu").pack()
            )
        ]
    )
    if callback.message:
        await callback.message.edit_text(
            "Выберите новое время:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await callback.answer()


@router.callback_query(AdminStates.reschedule_slot, AdminCallback.filter(F.action == "offer_slot"))
async def offer_slot(
    callback: CallbackQuery,
    callback_data: AdminCallback,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    data = await state.get_data()
    booking_id = data.get("admin_reschedule_booking_id")
    if not booking_id:
        await callback.answer("Выберите заявку заново.", show_alert=True)
        return
    try:
        booking = await BookingService(session).propose_reschedule(
            UUID(booking_id), UUID(callback_data.entity_id), db_user.id
        )
    except (LookupError, SlotUnavailableError, InvalidTransitionError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    owner = await session.get(User, booking.user_id)
    slot = await session.get(TimeSlot, booking.proposed_slot_id)
    if owner and slot:
        await callback.bot.send_message(
            owner.telegram_id,
            f"Студия предлагает другое время: {format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE)}. Подходит?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подходит",
                            callback_data=BookingCallback(
                                action="offer_accept", value=str(booking.id)
                            ).pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Выбрать другое время",
                            callback_data=BookingCallback(
                                action="offer_decline", value=str(booking.id)
                            ).pack(),
                        )
                    ],
                ]
            ),
        )
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            "Предложение отправлено клиенту.", reply_markup=admin_menu()
        )
    await callback.answer()
