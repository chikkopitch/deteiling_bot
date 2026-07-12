from datetime import date
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import AvailableSlot


class MyAppointmentCallback(CallbackData, prefix="ma"):
    action: str
    appointment_id: UUID | None = None
    value: str = "-"


def categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Активные",
                    callback_data=MyAppointmentCallback(
                        action="list", value="active"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Завершённые",
                    callback_data=MyAppointmentCallback(
                        action="list", value="completed"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отменённые",
                    callback_data=MyAppointmentCallback(
                        action="list", value="cancelled"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Главное меню", callback_data="navigation:main"
                )
            ],
        ]
    )


def appointments_keyboard(items) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{str(item.id)[:8]} · {item.status.value}",
                callback_data=MyAppointmentCallback(
                    action="open", appointment_id=item.id
                ).pack(),
            )
        ]
        for item in items
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← Разделы",
                callback_data=MyAppointmentCallback(action="root").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def appointment_actions_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Перенести",
                    callback_data=MyAppointmentCallback(
                        action="reschedule", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=MyAppointmentCallback(
                        action="cancel", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Связаться с менеджером",
                    callback_data=MyAppointmentCallback(
                        action="manager", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=MyAppointmentCallback(action="root").pack(),
                )
            ],
        ]
    )


def dates_keyboard(appointment_id: UUID, dates: list[date]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=value.strftime("%d.%m.%Y"),
                callback_data=MyAppointmentCallback(
                    action="date",
                    appointment_id=appointment_id,
                    value=value.isoformat(),
                ).pack(),
            )
        ]
        for value in dates
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← Назад",
                callback_data=MyAppointmentCallback(
                    action="open", appointment_id=appointment_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_keyboard(
    appointment_id: UUID, slots: list[AvailableSlot], timezone
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=slot.starts_at.astimezone(timezone).strftime("%H:%M"),
                callback_data=MyAppointmentCallback(
                    action="slot", appointment_id=appointment_id, value=str(slot.id)
                ).pack(),
            )
            for slot in slots[i : i + 3]
        ]
        for i in range(0, len(slots), 3)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← К датам",
                callback_data=MyAppointmentCallback(
                    action="reschedule", appointment_id=appointment_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


CANCEL_REASONS = {
    "plans": "Изменились планы",
    "time": "Не подходит время",
    "price": "Дорого",
    "other_studio": "Выбрал другую студию",
    "other": "Другое",
}


def cancellation_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=text,
                callback_data=MyAppointmentCallback(
                    action="cc", appointment_id=appointment_id, value=code
                ).pack(),
            )
        ]
        for code, text in CANCEL_REASONS.items()
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← Назад",
                callback_data=MyAppointmentCallback(
                    action="open", appointment_id=appointment_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reschedule_confirmation_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить перенос",
                    callback_data=MyAppointmentCallback(
                        action="rc", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Выбрать другое время",
                    callback_data=MyAppointmentCallback(
                        action="reschedule", appointment_id=appointment_id
                    ).pack(),
                )
            ],
        ]
    )
