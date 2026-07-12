"""Main menu commands, placeholders, and nested back navigation."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import (
    BOOK_INSPECTION,
    CALCULATE_PRICE,
    back_to_menu_keyboard,
    main_menu_keyboard,
)
from app.database.models import User
from app.services.user_entry import UserEntryService

router = Router(name="menu")


async def send_main_menu(message: Message, text: str = "Главное меню") -> None:
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("menu"))
async def handle_menu(message: Message) -> None:
    await send_main_menu(message)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/start — начать работу или восстановить черновик;\n"
        "/menu — открыть главное меню;\n"
        "/help — показать помощь;\n"
        "/cancel — отменить текущий незавершённый сценарий.\n\n"
        "Команда /cancel не отменяет подтверждённую запись.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(Command("cancel"))
async def handle_cancel(
    message: Message, app_user: User, session: AsyncSession
) -> None:
    cancelled = await UserEntryService(session).cancel_current(app_user)
    text = (
        "Текущий сценарий отменён. Временный резерв освобождён."
        if cancelled
        else "Активного незавершённого сценария нет."
    )
    await send_main_menu(message, text)


@router.callback_query(F.data == "navigation:main")
async def navigate_to_main(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())


@router.message(F.text == BOOK_INSPECTION)
async def begin_inspection_booking(
    message: Message, app_user: User, session: AsyncSession
) -> None:
    service = UserEntryService(session)
    context = await service.load_context(app_user)
    if context.draft is not None:
        from app.bot.keyboards import draft_recovery_keyboard

        await message.answer(
            "У вас уже есть незавершённая заявка.",
            reply_markup=draft_recovery_keyboard(context.draft.id),
        )
        return
    _, state = await service.begin_booking(app_user)
    from app.bot.handlers.vehicle import render_vehicle_step

    await render_vehicle_step(message, app_user, session, state)


@router.message(F.text == CALCULATE_PRICE)
async def begin_price_calculation(
    message: Message, app_user: User, session: AsyncSession
) -> None:
    from app.bot.handlers.vehicle import render_vehicle_step
    from app.services.vehicle_selection import VehicleSelectionService

    state = await VehicleSelectionService(session).start_price_calculation(app_user)
    await render_vehicle_step(message, app_user, session, state)


SECTION_TEXTS = {}


@router.message(F.text.in_(set(SECTION_TEXTS)))
async def show_section(message: Message) -> None:
    await message.answer(
        SECTION_TEXTS[message.text],
        reply_markup=back_to_menu_keyboard(),
    )
