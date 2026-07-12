"""Reply and inline navigation keyboards."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BOOK_INSPECTION = "Записаться на бесплатный осмотр"
CALCULATE_PRICE = "Рассчитать стоимость"
SERVICES = "Услуги"
MY_APPOINTMENTS = "Мои записи"
FAQ = "Частые вопросы"
CONTACT_MANAGER = "Связаться с менеджером"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BOOK_INSPECTION)],
            [KeyboardButton(text=CALCULATE_PRICE), KeyboardButton(text=SERVICES)],
            [KeyboardButton(text=MY_APPOINTMENTS), KeyboardButton(text=FAQ)],
            [KeyboardButton(text=CONTACT_MANAGER)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="navigation:main")]
        ]
    )
