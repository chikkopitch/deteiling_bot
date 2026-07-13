"""Vehicle brand/model/class/year selection handlers."""

from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import ConversationStepFilter
from app.bot.keyboards import VehicleCallback, main_menu_keyboard
from app.bot.keyboards.vehicle import (
    brands_keyboard,
    classes_keyboard,
    models_keyboard,
    text_input_keyboard,
    vehicle_input_keyboard,
    year_keyboard,
)
from app.database.models import ConversationState, User
from app.services.user_entry import UserEntryService
from app.services.vehicle_selection import (
    FLOW_CODES,
    VehicleSelectionError,
    VehicleSelectionService,
    clean_user_text,
)

router = Router(name="vehicle")


def _flow(code: str) -> str:
    flow = FLOW_CODES.get(code)
    if flow is None:
        raise VehicleSelectionError("Неизвестный сценарий. Начните заново.")
    return flow


async def show_brands(
    message: Message, user: User, session: AsyncSession, flow_code: str, page: int = 0
) -> None:
    page_data = await VehicleSelectionService(session).brands_page(
        user.id, _flow(flow_code), page
    )
    text = "Выберите марку автомобиля:"
    if page_data.search:
        text += f"\nРезультаты поиска: <b>{page_data.search}</b>"
    if not page_data.items:
        text += "\nНичего не найдено. Измените поиск или выберите другую марку."
    await message.answer(text, reply_markup=brands_keyboard(flow_code, page_data))


async def show_models(
    message: Message, user: User, session: AsyncSession, flow_code: str, page: int = 0
) -> None:
    page_data = await VehicleSelectionService(session).models_page(
        user.id, _flow(flow_code), page
    )
    text = "Выберите модель автомобиля:"
    if page_data.search:
        text += f"\nРезультаты поиска: <b>{page_data.search}</b>"
    if not page_data.items:
        text += "\nНичего не найдено. Измените поиск или укажите другую модель."
    await message.answer(text, reply_markup=models_keyboard(flow_code, page_data))


async def show_classes(message: Message, session: AsyncSession, flow_code: str) -> None:
    classes = await VehicleSelectionService(session).list_classes()
    await message.answer(
        "Выберите класс автомобиля:",
        reply_markup=classes_keyboard(flow_code, classes),
    )


async def show_year(message: Message, flow_code: str) -> None:
    await message.answer(
        "Введите год выпуска четырьмя цифрами или нажмите «Пропустить»:",
        reply_markup=year_keyboard(flow_code),
    )


async def render_vehicle_step(
    message: Message,
    user: User,
    session: AsyncSession,
    state: ConversationState,
) -> None:
    flow_code = next(
        (code for code, name in FLOW_CODES.items() if name == state.flow), None
    )
    if flow_code is None:
        await message.answer(
            "Сценарий больше не поддерживается.", reply_markup=main_menu_keyboard()
        )
        return
    if state.step == "vehicle_input":
        await message.answer(
            "Введите марку и модель автомобиля одним сообщением, например: BMW X5.",
            reply_markup=vehicle_input_keyboard(flow_code),
        )
    elif state.step == "vehicle_brand":
        await show_brands(message, user, session, flow_code)
    elif state.step == "vehicle_brand_search":
        await message.answer(
            "Введите часть названия марки:",
            reply_markup=text_input_keyboard(flow_code, "br"),
        )
    elif state.step == "vehicle_model":
        await show_models(message, user, session, flow_code)
    elif state.step == "vehicle_model_search":
        await message.answer(
            "Введите часть названия модели:",
            reply_markup=text_input_keyboard(flow_code, "mo"),
        )
    elif state.step == "custom_vehicle_brand":
        await message.answer(
            "Введите марку автомобиля:",
            reply_markup=text_input_keyboard(flow_code, "br"),
        )
    elif state.step == "custom_vehicle_model":
        await message.answer(
            "Введите модель автомобиля:",
            reply_markup=text_input_keyboard(flow_code, "mo"),
        )
    elif state.step == "vehicle_class":
        await show_classes(message, session, flow_code)
    elif state.step == "vehicle_year":
        await show_year(message, flow_code)
    elif state.step == "photo_upload":
        # Drafts created before photo uploads were removed continue at the date step.
        state = await VehicleSelectionService(session).set_step(
            user, state.flow, "date_selection"
        )
        from app.bot.handlers.services import render_service_step

        await render_service_step(message, user, session, state)
    elif state.step in {
        "service_selection",
        "price_services",
        "price_result",
        "date_selection",
    }:
        from app.bot.handlers.services import render_service_step

        await render_service_step(message, user, session, state)
    elif state.step in {
        "contact_name",
        "contact_name_input",
        "contact_phone",
        "contact_phone_input",
        "review",
    }:
        from app.bot.handlers.contacts import render_contact_step
        from app.core.config import get_settings

        await render_contact_step(message, user, session, get_settings(), state)
    else:
        await message.answer(
            "Данные автомобиля сохранены. Следующий этап будет добавлен далее.",
            reply_markup=main_menu_keyboard(),
        )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(VehicleCallback.filter())
async def handle_vehicle_callback(
    callback: CallbackQuery,
    callback_data: VehicleCallback,
    app_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        flow = _flow(callback_data.flow)
        service = VehicleSelectionService(session)
        entity, action, value = (
            callback_data.entity,
            callback_data.action,
            callback_data.value,
        )

        if entity == "flow" and action == "back":
            await callback.message.answer(
                "Главное меню", reply_markup=main_menu_keyboard()
            )
            return
        if entity == "flow" and action == "cancel":
            await UserEntryService(session).cancel_flow(app_user, flow)
            await callback.message.answer(
                "Сценарий отменён.", reply_markup=main_menu_keyboard()
            )
            return

        if entity == "br" and action == "page":
            await show_brands(
                callback.message, app_user, session, callback_data.flow, int(value)
            )
        elif entity == "br" and action == "search":
            await service.set_step(app_user, flow, "vehicle_brand_search")
            await callback.message.answer(
                "Введите часть названия марки:",
                reply_markup=text_input_keyboard(callback_data.flow, "br"),
            )
        elif entity == "br" and action == "custom":
            await service.request_custom_brand(app_user, flow)
            await callback.message.answer(
                "Введите марку автомобиля:",
                reply_markup=text_input_keyboard(callback_data.flow, "br"),
            )
        elif entity == "br" and action == "select":
            await service.select_brand(app_user, flow, UUID(value))
            await show_models(callback.message, app_user, session, callback_data.flow)
        elif entity == "br" and action == "back":
            await service.set_step(app_user, flow, "vehicle_brand", brand_search=None)
            await show_brands(callback.message, app_user, session, callback_data.flow)
        elif entity == "mo" and action == "page":
            await show_models(
                callback.message, app_user, session, callback_data.flow, int(value)
            )
        elif entity == "mo" and action == "search":
            await service.set_step(app_user, flow, "vehicle_model_search")
            await callback.message.answer(
                "Введите часть названия модели:",
                reply_markup=text_input_keyboard(callback_data.flow, "mo"),
            )
        elif entity == "mo" and action == "custom":
            await service.request_custom_model(app_user, flow)
            await callback.message.answer(
                "Введите модель автомобиля:",
                reply_markup=text_input_keyboard(callback_data.flow, "mo"),
            )
        elif entity == "mo" and action == "select":
            await service.select_model(app_user, flow, UUID(value))
            await show_year(callback.message, callback_data.flow)
        elif entity == "mo" and action == "back":
            await service.set_step(app_user, flow, "vehicle_brand", model_search=None)
            await show_brands(callback.message, app_user, session, callback_data.flow)
        elif entity == "cl" and action == "select":
            await service.select_class(app_user, flow, UUID(value))
            await show_year(callback.message, callback_data.flow)
        elif entity == "cl" and action == "back":
            state = await service.get_state(app_user.id, flow)
            return_step = state.payload.get("class_return_step") if state else None
            if return_step == "custom_vehicle_model":
                await service.set_step(app_user, flow, "custom_vehicle_model")
                await callback.message.answer(
                    "Введите модель автомобиля:",
                    reply_markup=text_input_keyboard(callback_data.flow, "mo"),
                )
            else:
                await service.set_step(app_user, flow, "vehicle_model")
                await show_models(
                    callback.message, app_user, session, callback_data.flow
                )
        elif entity == "yr" and action == "skip":
            state = await service.save_year(app_user, flow, None)
            await render_vehicle_step(callback.message, app_user, session, state)
        elif entity == "yr" and action == "back":
            state = await service.get_state(app_user.id, flow)
            return_step = state.payload.get("year_return_step") if state else None
            if return_step == "vehicle_class":
                await service.set_step(app_user, flow, "vehicle_class")
                await show_classes(callback.message, session, callback_data.flow)
            else:
                await service.set_step(app_user, flow, "vehicle_model")
                await show_models(
                    callback.message, app_user, session, callback_data.flow
                )
        else:
            raise VehicleSelectionError("Кнопка устарела. Продолжите через /start.")
    except (VehicleSelectionError, ValueError) as error:
        await callback.message.answer(str(error), reply_markup=main_menu_keyboard())


TEXT_STEPS = (
    "vehicle_input",
    "vehicle_brand_search",
    "vehicle_model_search",
    "custom_vehicle_brand",
    "custom_vehicle_model",
    "vehicle_year",
)


@router.message(F.text, ConversationStepFilter(*TEXT_STEPS))
async def handle_vehicle_text(
    message: Message,
    app_user: User,
    session: AsyncSession,
    conversation_state: ConversationState,
    vehicle_flow_code: str,
) -> None:
    service = VehicleSelectionService(session)
    flow = conversation_state.flow
    try:
        if conversation_state.step == "vehicle_input":
            state = await service.save_vehicle_description(
                app_user, flow, message.text
            )
            from app.bot.handlers.services import render_service_step

            await render_service_step(message, app_user, session, state)
        elif conversation_state.step == "vehicle_brand_search":
            query = clean_user_text(message.text, max_length=100)
            await service.set_step(app_user, flow, "vehicle_brand", brand_search=query)
            await show_brands(message, app_user, session, vehicle_flow_code)
        elif conversation_state.step == "vehicle_model_search":
            query = clean_user_text(message.text, max_length=100)
            await service.set_step(app_user, flow, "vehicle_model", model_search=query)
            await show_models(message, app_user, session, vehicle_flow_code)
        elif conversation_state.step == "custom_vehicle_brand":
            await service.save_custom_brand(app_user, flow, message.text)
            await message.answer(
                "Введите модель автомобиля:",
                reply_markup=text_input_keyboard(vehicle_flow_code, "mo"),
            )
        elif conversation_state.step == "custom_vehicle_model":
            await service.save_custom_model(app_user, flow, message.text)
            await show_classes(message, session, vehicle_flow_code)
        elif conversation_state.step == "vehicle_year":
            state = await service.save_year(app_user, flow, message.text)
            await render_vehicle_step(message, app_user, session, state)
    except VehicleSelectionError as error:
        keyboard = (
            year_keyboard(vehicle_flow_code)
            if conversation_state.step == "vehicle_year"
            else (
                vehicle_input_keyboard(vehicle_flow_code)
                if conversation_state.step == "vehicle_input"
                else text_input_keyboard(
                    vehicle_flow_code,
                    "br" if "brand" in conversation_state.step else "mo",
                )
            )
        )
        await message.answer(str(error), reply_markup=keyboard)
