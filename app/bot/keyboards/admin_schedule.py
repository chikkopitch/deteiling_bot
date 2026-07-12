"""Inline keyboards for managing bookable time slots."""

from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import AvailableSlot


class AdminScheduleCallback(CallbackData, prefix="admsch"):
    action: str
    value: str = "-"


def admin_schedule_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить время",
                    callback_data=AdminScheduleCallback(action="add").pack(),
                ),
                InlineKeyboardButton(
                    text="📋 Ближайшие слоты",
                    callback_data=AdminScheduleCallback(action="list").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К админке",
                    callback_data=AdminScheduleCallback(action="menu").pack(),
                )
            ],
        ]
    )


def admin_schedule_slots_keyboard(
    slots: list[AvailableSlot], timezone: ZoneInfo
) -> InlineKeyboardMarkup:
    rows = []
    for slot in slots:
        starts_at = slot.starts_at.astimezone(timezone)
        ends_at = slot.ends_at.astimezone(timezone)
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"Закрыть {starts_at:%d.%m %H:%M}–{ends_at:%H:%M}"
                    ),
                    callback_data=AdminScheduleCallback(
                        action="close", value=str(slot.id)
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить время",
                callback_data=AdminScheduleCallback(action="add").pack(),
            ),
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=AdminScheduleCallback(action="menu").pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)

