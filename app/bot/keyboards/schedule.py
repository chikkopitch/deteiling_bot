"""Inline calendar and time keyboards."""

import calendar
from zoneinfo import ZoneInfo

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import AvailableSlot
from app.services.schedule import CalendarMonth

MONTH_NAMES = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


class ScheduleCallback(CallbackData, prefix="sch"):
    action: str
    value: str = "-"


def _callback(action: str, value: str = "-") -> str:
    return ScheduleCallback(action=action, value=value).pack()


def calendar_keyboard(data: CalendarMonth) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"{MONTH_NAMES[data.month]} {data.year}", callback_data="noop"
            )
        ],
        [
            InlineKeyboardButton(text=label, callback_data="noop")
            for label in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        ],
    ]
    month_calendar = calendar.Calendar(firstweekday=0)
    for week in month_calendar.monthdatescalendar(data.year, data.month):
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day.month != data.month:
                row.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            elif day in data.available_dates:
                row.append(
                    InlineKeyboardButton(
                        text=str(day.day),
                        callback_data=_callback("date", day.isoformat()),
                    )
                )
            else:
                row.append(InlineKeyboardButton(text="·", callback_data="noop"))
        rows.append(row)

    navigation: list[InlineKeyboardButton] = []
    if data.can_previous:
        previous_month = data.month - 1 or 12
        previous_year = data.year - (data.month == 1)
        navigation.append(
            InlineKeyboardButton(
                text="←",
                callback_data=_callback(
                    "month", f"{previous_year:04d}-{previous_month:02d}"
                ),
            )
        )
    if data.can_next:
        next_month = data.month % 12 + 1
        next_year = data.year + (data.month == 12)
        navigation.append(
            InlineKeyboardButton(
                text="→",
                callback_data=_callback("month", f"{next_year:04d}-{next_month:02d}"),
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                text="← Назад", callback_data=_callback("back_service")
            ),
            InlineKeyboardButton(text="Отменить", callback_data=_callback("cancel")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def times_keyboard(
    slots: list[AvailableSlot], timezone: ZoneInfo
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for slot in slots:
        current_row.append(
            InlineKeyboardButton(
                text=slot.starts_at.astimezone(timezone).strftime("%H:%M"),
                callback_data=_callback("slot", str(slot.id)),
            )
        )
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append(
        [
            InlineKeyboardButton(
                text="← К календарю", callback_data=_callback("back_calendar")
            ),
            InlineKeyboardButton(text="Отменить", callback_data=_callback("cancel")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
