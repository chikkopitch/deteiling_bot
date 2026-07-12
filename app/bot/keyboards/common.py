from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.keyboards.callbacks import BookingCallback, MenuCallback


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        ("🚗 Записаться на бесплатный осмотр", "booking"),
        ("✨ Услуги и цены", "services"),
        ("🧮 Рассчитать стоимость", "calculator"),
        ("📅 Моя запись", "my_booking"),
        ("❓ Частые вопросы", "faq"),
        ("💬 Связаться с менеджером", "manager"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=MenuCallback(section=value).pack())]
            for text, value in rows
        ]
    )


def navigation(
    *, back: str | None = None, cancel: bool = False
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    if back:
        rows.append(
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data=BookingCallback(action="back", value=back).pack()
                )
            ]
        )
    if cancel:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Отменить", callback_data=BookingCallback(action="cancel").pack()
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Главное меню", callback_data=MenuCallback(section="main").pack()
            )
        ]
    )
    return rows


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться номером", request_contact=True)],
            [KeyboardButton(text="Отменить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
