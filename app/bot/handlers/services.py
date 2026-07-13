"""Service selection and Telegram photo metadata handlers."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import ConversationStepFilter
from app.bot.keyboards import CalculatorCallback, ServiceCallback, main_menu_keyboard
from app.bot.keyboards.calculator import calculation_result_keyboard, factor_keyboard
from app.bot.keyboards.services import services_keyboard
from app.core.config import get_settings
from app.database.models import ConversationState, User
from app.services.service_selection import ServiceCard, ServiceSelectionService
from app.services.price_calculator import PriceCalculatorService
from app.services.user_entry import UserEntryService
from app.services.vehicle_selection import (
    FLOW_CODES,
    VehicleSelectionError,
    VehicleSelectionService,
)

router = Router(name="services_selection")


def _flow(code: str) -> str:
    flow = FLOW_CODES.get(code)
    if flow is None:
        raise VehicleSelectionError("Неизвестный сценарий. Начните заново.")
    return flow


def _money(value: Decimal) -> str:
    rendered = f"{value:,.2f}".replace(",", " ").replace(".00", "")
    return f"{rendered} {get_settings().currency_symbol}"


def _card_text(index: int, card: ServiceCard) -> str:
    if card.price_from == card.price_to:
        price = _money(card.price_from)
    else:
        price = f"от {_money(card.price_from)} до {_money(card.price_to)}"
    description = card.service.short_description or "Описание уточняется."
    return (
        f"<b>{index}. {card.service.name}</b>\n"
        f"{description}\n"
        f"Ориентировочная цена: {price}\n"
        f"Длительность: {card.service.duration_minutes} мин."
    )


async def show_services(
    message: Message,
    user: User,
    session: AsyncSession,
    flow_code: str,
    page_number: int = 0,
) -> None:
    page = await ServiceSelectionService(session).page(
        user, _flow(flow_code), page_number
    )
    text = "\n\n".join(
        _card_text(page.page * 5 + index, card)
        for index, card in enumerate(page.cards, start=1)
    )
    if not text:
        text = "Активные услуги пока не настроены."
    await message.answer(text, reply_markup=services_keyboard(flow_code, page))


async def show_price_result(message: Message, state: ConversationState) -> None:
    price_from = Decimal(str(state.payload["estimated_price_from"]))
    price_to = Decimal(str(state.payload["estimated_price_to"]))
    price = (
        _money(price_from)
        if price_from == price_to
        else f"от {_money(price_from)} до {_money(price_to)}"
    )
    vehicle = (
        " ".join(
            filter(
                None,
                (
                    state.payload.get("vehicle_brand_name")
                    or state.payload.get("custom_vehicle_brand"),
                    state.payload.get("vehicle_model_name")
                    or state.payload.get("custom_vehicle_model"),
                    str(state.payload.get("vehicle_year") or ""),
                ),
            )
        )
        or "Не указан"
    )
    selections = [
        f"• {(values[0].get('factor_name') if values else key)}: {', '.join(item['label'] for item in values) or 'нет'}"
        for key, values in state.payload.get("factor_selections", {}).items()
    ]
    parameters = "\n".join(selections) or "Дополнительные параметры не применялись."
    await message.answer(
        f"Услуга: <b>{state.payload.get('service_name', 'выбрана')}</b>\n"
        f"Автомобиль: <b>{vehicle}</b>\n"
        f"Параметры:\n{parameters}\n"
        f"Предварительная стоимость: <b>{price}</b>\n\n"
        "Точная стоимость определяется после осмотра.",
        reply_markup=calculation_result_keyboard(),
    )


async def show_factor(message: Message, user: User, session: AsyncSession) -> None:
    calculator = PriceCalculatorService(session)
    step = await calculator.current_step(user)
    if step is None:
        state, _ = await calculator.calculate(user)
        await show_price_result(message, state)
        return
    await message.answer(
        f"Параметр {step.index + 1} из {step.total}: <b>{step.factor.name}</b>",
        reply_markup=factor_keyboard(
            step.values,
            multiple=step.factor.input_type == "multiple",
            selected={
                item["value_id"]
                for item in (await calculator._state(user))
                .payload.get("factor_selections", {})
                .get(step.factor.key, [])
            },
        ),
    )


async def render_service_step(
    message: Message,
    user: User,
    session: AsyncSession,
    state: ConversationState,
) -> None:
    flow_code = next(
        (code for code, name in FLOW_CODES.items() if name == state.flow), None
    )
    if flow_code is None:
        await message.answer("Сценарий устарел.", reply_markup=main_menu_keyboard())
    elif state.step in {"service_selection", "price_services"}:
        preferred = state.payload.get("preferred_service_id")
        if preferred:
            try:
                selected = await ServiceSelectionService(session).select(
                    user, state.flow, UUID(str(preferred))
                )
                await render_service_step(message, user, session, selected)
                return
            except (ValueError, VehicleSelectionError):
                pass
        await show_services(message, user, session, flow_code)
    elif state.step == "price_result":
        await show_price_result(message, state)
    elif state.step == "price_factors":
        await show_factor(message, user, session)
    elif state.step == "date_selection":
        from app.bot.handlers.schedule import render_schedule_step

        await render_schedule_step(message, user, session, get_settings(), state)


@router.callback_query(ServiceCallback.filter())
async def handle_service_callback(
    callback: CallbackQuery,
    callback_data: ServiceCallback,
    app_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        flow = _flow(callback_data.flow)
        service = ServiceSelectionService(session)
        if callback_data.action == "page":
            await show_services(
                callback.message,
                app_user,
                session,
                callback_data.flow,
                int(callback_data.value),
            )
            return
        if callback_data.action == "select":
            state = await service.select(app_user, flow, UUID(callback_data.value))
        elif callback_data.action == "free":
            state = await service.select_free_inspection(
                app_user, flow, consultation=False
            )
        elif callback_data.action == "consult":
            state = await service.select_free_inspection(
                app_user, flow, consultation=True
            )
        elif callback_data.action == "back":
            state = await VehicleSelectionService(session).set_step(
                app_user, flow, "vehicle_input" if flow == "booking" else "vehicle_year"
            )
            from app.bot.handlers.vehicle import render_vehicle_step

            await render_vehicle_step(callback.message, app_user, session, state)
            return
        elif callback_data.action == "cancel":
            await UserEntryService(session).cancel_flow(app_user, flow)
            await callback.message.answer(
                "Сценарий отменён.", reply_markup=main_menu_keyboard()
            )
            return
        else:
            raise VehicleSelectionError("Кнопка устарела.")
        await render_service_step(callback.message, app_user, session, state)
    except (VehicleSelectionError, ValueError) as error:
        await callback.message.answer(str(error), reply_markup=main_menu_keyboard())

@router.callback_query(CalculatorCallback.filter())
async def handle_calculator(
    callback: CallbackQuery,
    callback_data: CalculatorCallback,
    app_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    calculator = PriceCalculatorService(session)
    try:
        if callback_data.action == "v":
            state = await calculator.select_value(app_user, UUID(callback_data.value))
            await render_service_step(callback.message, app_user, session, state)
        elif callback_data.action == "done":
            state = await calculator.finish_multiple(app_user)
            await render_service_step(callback.message, app_user, session, state)
        elif callback_data.action == "restart":
            state = await VehicleSelectionService(session).start_price_calculation(
                app_user
            )
            from app.bot.handlers.vehicle import render_vehicle_step

            await render_vehicle_step(callback.message, app_user, session, state)
        elif callback_data.action == "book":
            calc_state = await calculator._state(app_user)
            appointment, booking_state = await UserEntryService(session).begin_booking(
                app_user
            )
            payload = dict(booking_state.payload)
            for key in (
                "vehicle_brand_id",
                "vehicle_model_id",
                "vehicle_class_id",
                "custom_vehicle_brand",
                "custom_vehicle_model",
                "vehicle_year",
            ):
                payload[key] = calc_state.payload.get(key)
            appointment.vehicle_brand_id = (
                UUID(payload["vehicle_brand_id"])
                if payload.get("vehicle_brand_id")
                else None
            )
            appointment.vehicle_model_id = (
                UUID(payload["vehicle_model_id"])
                if payload.get("vehicle_model_id")
                else None
            )
            appointment.vehicle_class_id = UUID(payload["vehicle_class_id"])
            appointment.custom_vehicle_brand = payload.get("custom_vehicle_brand")
            appointment.custom_vehicle_model = payload.get("custom_vehicle_model")
            appointment.vehicle_year = payload.get("vehicle_year")
            appointment.service_id = UUID(calc_state.payload["service_id"])
            appointment.estimated_price_from = Decimal(
                calc_state.payload["estimated_price_from"]
            )
            appointment.estimated_price_to = Decimal(
                calc_state.payload["estimated_price_to"]
            )
            payload.update(
                service_id=calc_state.payload["service_id"],
                service_name=calc_state.payload.get("service_name"),
                estimated_price_from=calc_state.payload["estimated_price_from"],
                estimated_price_to=calc_state.payload["estimated_price_to"],
                calculation_id=calc_state.payload.get("calculation_id"),
            )
            state = await VehicleSelectionService(session).states.upsert(
                user_id=app_user.id,
                flow="booking",
                step="date_selection",
                payload=payload,
                expires_at=booking_state.expires_at,
            )
            await render_service_step(callback.message, app_user, session, state)
        elif callback_data.action == "manager":
            await callback.message.answer(
                "Откройте раздел «Связаться с менеджером» в главном меню."
            )
        elif callback_data.action == "cancel":
            await UserEntryService(session).cancel_flow(app_user, "price_calculation")
            await callback.message.answer(
                "Расчёт отменён.", reply_markup=main_menu_keyboard()
            )
    except (VehicleSelectionError, ValueError) as error:
        await callback.message.answer(str(error), reply_markup=main_menu_keyboard())
