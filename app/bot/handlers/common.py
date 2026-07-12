"""Fallback for unsupported messages."""

from aiogram import Router
from aiogram.types import Message

from app.bot.keyboards import main_menu_keyboard

router = Router(name="common")


@router.message()
async def handle_unknown_message(message: Message) -> None:
    await message.answer(
        "Не удалось распознать действие. Выберите раздел главного меню.",
        reply_markup=main_menu_keyboard(),
    )
