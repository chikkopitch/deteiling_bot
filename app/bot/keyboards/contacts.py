"""Contact collection and final review keyboards."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

MANUAL_PHONE_TEXT = "Ввести номер вручную"


class ContactCallback(CallbackData, prefix="contact"):
    action: str


class ReviewCallback(CallbackData, prefix="review"):
    action: str


def name_keyboard(has_suggestion: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_suggestion:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Подтвердить имя",
                    callback_data=ContactCallback(action="confirm_name").pack(),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Ввести другое имя",
                    callback_data=ContactCallback(action="other_name").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=ContactCallback(action="back_time").pack(),
                ),
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=ContactCallback(action="cancel").pack(),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправить мой контакт", request_contact=True)],
            [KeyboardButton(text=MANUAL_PHONE_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Отправьте контакт или введите номер",
    )


def phone_navigation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="← Назад к имени",
                    callback_data=ContactCallback(action="back_name").pack(),
                ),
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=ContactCallback(action="cancel").pack(),
                ),
            ]
        ]
    )


def review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить заявку",
                    callback_data=ReviewCallback(action="submit").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить автомобиль",
                    callback_data=ReviewCallback(action="vehicle").pack(),
                ),
                InlineKeyboardButton(
                    text="Изменить услугу",
                    callback_data=ReviewCallback(action="service").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить время",
                    callback_data=ReviewCallback(action="time").pack(),
                ),
                InlineKeyboardButton(
                    text="Изменить контакты",
                    callback_data=ReviewCallback(action="contacts").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отменить заполнение",
                    callback_data=ReviewCallback(action="cancel").pack(),
                )
            ],
        ]
    )
