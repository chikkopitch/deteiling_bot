"""Public start and fallback handlers."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    DraftActionCallback,
    draft_recovery_keyboard,
    main_menu_keyboard,
)
from app.database.models import User
from app.services.user_entry import UserEntryService

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, app_user: User, session: AsyncSession) -> None:
    """Show a database-backed welcome and recover an unfinished draft."""
    context = await UserEntryService(session).load_context(app_user)
    if context.draft is not None:
        await message.answer(
            f"{context.welcome_text}\n\nУ вас есть незавершённая заявка. Что сделать?",
            reply_markup=draft_recovery_keyboard(context.draft.id),
        )
        return

    await message.answer(context.welcome_text, reply_markup=main_menu_keyboard())


@router.callback_query(DraftActionCallback.filter(F.action == "continue"))
async def continue_draft(
    callback: CallbackQuery,
    callback_data: DraftActionCallback,
    app_user: User,
    session: AsyncSession,
) -> None:
    result = await UserEntryService(session).resume_booking(
        app_user, callback_data.appointment_id
    )
    await callback.answer()
    if callback.message is None:
        return
    if result is None:
        await callback.message.answer(
            "Черновик уже закрыт или недоступен.", reply_markup=main_menu_keyboard()
        )
        return
    _, state = result
    await callback.message.answer("Черновик восстановлен.")
    from app.bot.handlers.vehicle import render_vehicle_step

    await render_vehicle_step(callback.message, app_user, session, state)


@router.callback_query(DraftActionCallback.filter(F.action == "restart"))
async def restart_draft(
    callback: CallbackQuery,
    callback_data: DraftActionCallback,
    app_user: User,
    session: AsyncSession,
) -> None:
    _, state = await UserEntryService(session).restart_booking(
        app_user, callback_data.appointment_id
    )
    await callback.answer("Создан новый черновик")
    if callback.message is not None:
        await callback.message.answer("Начинаем новую заявку.")
        from app.bot.handlers.vehicle import render_vehicle_step

        await render_vehicle_step(callback.message, app_user, session, state)


@router.callback_query(DraftActionCallback.filter(F.action == "delete"))
async def delete_draft(
    callback: CallbackQuery,
    callback_data: DraftActionCallback,
    app_user: User,
    session: AsyncSession,
) -> None:
    closed = await UserEntryService(session).close_draft(
        app_user.id, callback_data.appointment_id, "draft_deleted"
    )
    await callback.answer("Черновик закрыт" if closed else "Черновик уже закрыт")
    if callback.message is not None:
        await callback.message.answer(
            "Черновик закрыт. Выберите раздел:",
            reply_markup=main_menu_keyboard(),
        )
