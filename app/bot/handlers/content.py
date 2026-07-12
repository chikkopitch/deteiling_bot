from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.content import (
    ContentCallback,
    faq_answer_keyboard,
    faq_categories_keyboard,
    faq_items_keyboard,
    services_catalog_keyboard,
)
from app.bot.keyboards.main_menu import FAQ, SERVICES
from app.database.models import FAQItem, Service, ServicePrice, User
from app.database.repositories import (
    ConversationStateRepository,
    FAQRepository,
    ServiceRepository,
)
from app.services.faq import rank_faq
from app.services.user_entry import UserEntryService
from app.services.vehicle_selection import VehicleSelectionService

router = Router(name="content")
PAGE = 5


async def _categories(session):
    result = await session.execute(
        select(FAQItem.category)
        .where(FAQItem.is_active.is_(True), FAQItem.category.is_not(None))
        .distinct()
        .order_by(FAQItem.category)
    )
    return list(result.scalars())


async def show_catalog(message, session, page=0):
    items, total = await ServiceRepository(session).list_page(
        offset=max(page, 0) * PAGE, limit=PAGE
    )
    pages = max(1, ceil(total / PAGE))
    page = min(max(page, 0), pages - 1)
    blocks = []
    for service in items:
        bounds = await session.execute(
            select(
                func.min(func.coalesce(ServicePrice.min_price, ServicePrice.price)),
                func.max(func.coalesce(ServicePrice.max_price, ServicePrice.price)),
            ).where(ServicePrice.service_id == service.id)
        )
        low, high = bounds.one()
        low = low if low is not None else service.base_price
        high = high if high is not None else service.base_price
        blocks.append(
            f"<b>{service.name}</b>\n{service.full_description or service.short_description or 'Описание уточняется.'}\nЦена: от {low:.2f} до {high:.2f}\nДлительность: {service.duration_minutes} мин."
        )
    await message.answer(
        "\n\n".join(blocks) or "Активных услуг пока нет.",
        reply_markup=services_catalog_keyboard(items, page, pages),
    )


async def show_faq_root(message, session):
    await message.answer(
        "Выберите категорию:",
        reply_markup=faq_categories_keyboard(await _categories(session)),
    )


@router.message(F.text == SERVICES)
async def catalog(message: Message, session: AsyncSession):
    await show_catalog(message, session)


@router.message(F.text == FAQ)
async def faq_root(message: Message, session: AsyncSession):
    await show_faq_root(message, session)


@router.callback_query(ContentCallback.filter())
async def content_callback(
    callback: CallbackQuery,
    callback_data: ContentCallback,
    app_user: User,
    session: AsyncSession,
):
    await callback.answer()
    if callback.message is None:
        return
    action = callback_data.action
    if action == "services":
        await show_catalog(callback.message, session, callback_data.page)
    elif action == "faqroot":
        await show_faq_root(callback.message, session)
    elif action == "faqcat":
        categories = await _categories(session)
        index = int(callback_data.value)
        if index < 0 or index >= len(categories):
            return await callback.message.answer("Категория больше недоступна.")
        category = categories[index]
        items = await FAQRepository(session).list_active(category)
        pages = max(1, ceil(len(items) / PAGE))
        page = min(max(callback_data.page, 0), pages - 1)
        chunk = items[page * PAGE : (page + 1) * PAGE]
        await callback.message.answer(
            category, reply_markup=faq_items_keyboard(chunk, index, page, pages)
        )
    elif action == "faqitem":
        item = await session.get(FAQItem, UUID(callback_data.value))
        if item and item.is_active:
            await callback.message.answer(
                f"<b>{item.question}</b>\n\n{item.answer}",
                reply_markup=faq_answer_keyboard(),
            )
    elif action == "faqsearch":
        await ConversationStateRepository(session).upsert(
            user_id=app_user.id,
            flow="faq_search",
            step="query",
            payload={},
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        await callback.message.answer("Введите запрос для поиска по FAQ:")
    elif action in {"book", "calc"}:
        service = await session.get(Service, UUID(callback_data.value))
        if service is None or not service.is_active:
            return await callback.message.answer("Услуга больше недоступна.")
        if action == "book":
            _, state = await UserEntryService(session).begin_booking(app_user)
            state.payload["preferred_service_id"] = str(service.id)
        else:
            state = await VehicleSelectionService(session).start_price_calculation(
                app_user
            )
            state.payload["preferred_service_id"] = str(service.id)
        await session.flush()
        from app.bot.handlers.vehicle import render_vehicle_step

        await render_vehicle_step(callback.message, app_user, session, state)
    elif action == "manager":
        await callback.message.answer(
            "Откройте раздел «Связаться с менеджером» в главном меню."
        )


class FAQSearchFilter(BaseFilter):
    async def __call__(self, message: Message, app_user: User, session: AsyncSession):
        state = await ConversationStateRepository(session).get_active_for_flow(
            app_user.id, "faq_search", datetime.now(UTC)
        )
        return state is not None and state.step == "query"


@router.message(F.text & ~F.text.startswith("/"), FAQSearchFilter())
async def faq_search(message: Message, app_user: User, session: AsyncSession):
    results = rank_faq(await FAQRepository(session).list_active(), message.text or "")[
        :10
    ]
    state = await ConversationStateRepository(session).get_for_flow(
        app_user.id, "faq_search"
    )
    if state:
        await session.delete(state)
    if not results:
        return await message.answer(
            "По вашему запросу ничего не найдено.",
            reply_markup=faq_categories_keyboard(await _categories(session)),
        )
    await message.answer(
        "Результаты поиска:", reply_markup=faq_items_keyboard(results, 0, 0, 1)
    )
