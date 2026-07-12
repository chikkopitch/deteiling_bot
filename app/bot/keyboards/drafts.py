"""Draft recovery keyboard and callback schema."""

from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class DraftActionCallback(CallbackData, prefix="draft"):
    action: str
    appointment_id: UUID


def draft_recovery_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Продолжить",
                    callback_data=DraftActionCallback(
                        action="continue", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Начать заново",
                    callback_data=DraftActionCallback(
                        action="restart", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Удалить черновик",
                    callback_data=DraftActionCallback(
                        action="delete", appointment_id=appointment_id
                    ).pack(),
                )
            ],
        ]
    )
