from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class CalculatorCallback(CallbackData, prefix="calc"):
    action: str
    value: str = "-"


def factor_keyboard(
    values, *, multiple: bool = False, selected: set[str] | None = None
) -> InlineKeyboardMarkup:
    selected = selected or set()
    rows = [
        [
            InlineKeyboardButton(
                text=("✓ " if str(value.id) in selected else "") + value.label,
                callback_data=CalculatorCallback(
                    action="v", value=str(value.id)
                ).pack(),
            )
        ]
        for value in values
    ]
    if multiple:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Готово",
                    callback_data=CalculatorCallback(action="done").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Отменить",
                callback_data=CalculatorCallback(action="cancel").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calculation_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Записаться на бесплатный осмотр",
                    callback_data=CalculatorCallback(action="book").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Связаться с менеджером",
                    callback_data=CalculatorCallback(action="manager").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Пересчитать",
                    callback_data=CalculatorCallback(action="restart").pack(),
                )
            ],
        ]
    )
