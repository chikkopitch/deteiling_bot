from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu
from app.bot.keyboards.callbacks import BookingCallback, MenuCallback

router = Router(name="start")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Добро пожаловать! Бесплатный осмотр поможет оценить состояние автомобиля и подобрать уход без лишних услуг.",
        reply_markup=main_menu(),
    )


@router.callback_query(MenuCallback.filter(F.section == "main"))
async def menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Что хотите сделать?", reply_markup=main_menu())
    await callback.answer()


@router.message(F.text == "Отменить")
async def cancel_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu())


@router.callback_query(BookingCallback.filter(F.action == "cancel"))
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Действие отменено.", reply_markup=main_menu())
    await callback.answer()
