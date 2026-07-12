from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu

router = Router(name="fallback")


@router.callback_query()
async def old_callback(callback: CallbackQuery) -> None:
    await callback.answer("Эта кнопка устарела. Откройте меню заново.", show_alert=True)


@router.message()
async def unknown(message: Message) -> None:
    await message.answer("Не понял сообщение. Выберите действие в меню.", reply_markup=main_menu())
