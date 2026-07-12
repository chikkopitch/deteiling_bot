"""Administrative dashboard and appointment action keyboards."""

from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class AdminPanelCallback(CallbackData, prefix="admin"):
    section: str


class AdminApplicationCallback(CallbackData, prefix="admapp"):
    action: str
    appointment_id: UUID


class AdminChangeCallback(CallbackData, prefix="admchg"):
    action: str
    value: str = "-"


ADMIN_SECTIONS = (
    ("admins", "Администраторы"),
    ("roles", "Роли"),
    ("new", "Новые заявки"),
    ("today", "Сегодня"),
    ("tomorrow", "Завтра"),
    ("future", "Будущие записи"),
    ("all", "Все заявки"),
    ("schedule", "Расписание"),
    ("free_slots", "Свободные слоты"),
    ("services", "Услуги"),
    ("prices", "Цены"),
    ("calculator", "Калькулятор"),
    ("faq", "FAQ"),
    ("requests", "Запросы менеджеру"),
    ("clients", "Поиск клиента"),
    ("statistics", "Статистика"),
    ("settings", "Настройки"),
    ("audit", "Журнал действий"),
)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for index in range(0, len(ADMIN_SECTIONS), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=AdminPanelCallback(section=section).pack(),
                )
                for section, label in ADMIN_SECTIONS[index : index + 2]
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_application_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=AdminApplicationCallback(
                action=action, appointment_id=appointment_id
            ).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("Подтвердить", "confirm"), button("Отклонить", "reject")],
            [button("Предложить другое время", "reschedule")],
            [button("Написать клиенту", "write"), button("Открыть заявку", "open")],
        ]
    )
