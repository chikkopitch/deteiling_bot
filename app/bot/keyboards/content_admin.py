from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.content_admin import EDITABLE_CONTENT


class ContentAdminCallback(CallbackData, prefix="cadm"):
    action: str
    key: str


def content_settings_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ContentAdminCallback(action="edit", key=key).pack(),
                )
            ]
            for key, label in EDITABLE_CONTENT.items()
        ]
    )


def content_preview_keyboard(key):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сохранить",
                    callback_data=ContentAdminCallback(action="save", key=key).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить",
                    callback_data=ContentAdminCallback(action="edit", key=key).pack(),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=ContentAdminCallback(action="cancel", key=key).pack(),
                ),
            ],
        ]
    )
