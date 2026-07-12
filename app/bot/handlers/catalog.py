from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callbacks import (
    CatalogCallback,
    FAQCallback,
    FAQCategoryCallback,
    MenuCallback,
    ServiceCallback,
)
from app.bot.states import FAQStates
from app.models import FAQItem, Service
from app.repositories import CatalogRepository

router = Router(name="catalog")
PAGE_SIZE = 10


def footer(back: str = "main") -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton(text="← Назад", callback_data=MenuCallback(section=back).pack())],
        [
            InlineKeyboardButton(
                text="Главное меню", callback_data=MenuCallback(section="main").pack()
            )
        ],
    ]


@router.callback_query(MenuCallback.filter(F.section == "services"))
async def services(callback: CallbackQuery, session: AsyncSession) -> None:
    categories = await CatalogRepository(session).service_categories()
    rows = [
        [
            InlineKeyboardButton(
                text=item.name,
                callback_data=CatalogCallback(action="service_category", value=str(item.id)).pack(),
            )
        ]
        for item in categories
    ]
    rows.extend(footer())
    if callback.message:
        await callback.message.edit_text(
            "Услуги и цены:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(CatalogCallback.filter(F.action == "service_category"))
async def service_category(
    callback: CallbackQuery, callback_data: CatalogCallback, session: AsyncSession
) -> None:
    items = await CatalogRepository(session).services(
        limit=50, category_id=UUID(callback_data.value)
    )
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.name} — от {item.price_from:.0f} ₽",
                callback_data=ServiceCallback(item_id=str(item.id)).pack(),
            )
        ]
        for item in items
    ]
    rows.extend(footer("services"))
    if callback.message:
        await callback.message.edit_text(
            "Выберите услугу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(ServiceCallback.filter())
async def service_item(
    callback: CallbackQuery, callback_data: ServiceCallback, session: AsyncSession
) -> None:
    item = await session.get(Service, UUID(callback_data.item_id))
    if item is None or not item.is_active:
        await callback.answer("Услуга недоступна.", show_alert=True)
        return
    text = f"<b>{item.name}</b>\n\n{item.short_description}\n\nЧто входит: {item.includes or 'Уточнит специалист'}\nДлительность: около {item.duration_minutes} мин.\nЦена: от {item.price_from:.0f} ₽\nПодходит: {item.suitable_for}"
    rows = [
        [
            InlineKeyboardButton(
                text="Записаться", callback_data=MenuCallback(section="booking").pack()
            ),
            InlineKeyboardButton(
                text="Рассчитать стоимость",
                callback_data=CatalogCallback(
                    action="calculate_service", value=str(item.id)
                ).pack(),
            ),
        ],
        *footer("services"),
    ]
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
        )
    await callback.answer()


async def render_faq(
    callback: CallbackQuery, session: AsyncSession, category: str | None = None
) -> None:
    items = await CatalogRepository(session).faq(category=category, limit=PAGE_SIZE)
    rows = [
        [
            InlineKeyboardButton(
                text=item.question, callback_data=FAQCallback(item_id=str(item.id)).pack()
            )
        ]
        for item in items
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔎 Поиск", callback_data=CatalogCallback(action="faq_search").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="Не нашли ответ? Связаться с менеджером",
                    callback_data=MenuCallback(section="manager").pack(),
                )
            ],
            *footer(),
        ]
    )
    title = f"FAQ: {category}" if category else "Частые вопросы:"
    if callback.message:
        await callback.message.edit_text(
            title, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )


@router.callback_query(MenuCallback.filter(F.section == "faq"))
async def faq(callback: CallbackQuery, session: AsyncSession) -> None:
    categories = await CatalogRepository(session).faq_categories()
    rows = [
        [
            InlineKeyboardButton(
                text=item.title(), callback_data=FAQCategoryCallback(category=item).pack()
            )
        ]
        for item in categories
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔎 Поиск", callback_data=CatalogCallback(action="faq_search").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="Не нашли ответ? Связаться с менеджером",
                    callback_data=MenuCallback(section="manager").pack(),
                )
            ],
            *footer(),
        ]
    )
    if callback.message:
        await callback.message.edit_text(
            "Выберите категорию вопроса:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(FAQCategoryCallback.filter())
async def faq_category(
    callback: CallbackQuery, callback_data: FAQCategoryCallback, session: AsyncSession
) -> None:
    await render_faq(callback, session, callback_data.category)
    await callback.answer()


@router.callback_query(CatalogCallback.filter(F.action == "faq_search"))
async def faq_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FAQStates.search)
    if callback.message:
        await callback.message.edit_text("Напишите ключевое слово для поиска по FAQ:")
    await callback.answer()


@router.message(FAQStates.search)
async def faq_search_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    query = " ".join((message.text or "").split())
    if not query:
        await message.answer("Введите слово для поиска.")
        return
    items = await CatalogRepository(session).faq(query=query, limit=PAGE_SIZE)
    rows = [
        [
            InlineKeyboardButton(
                text=item.question, callback_data=FAQCallback(item_id=str(item.id)).pack()
            )
        ]
        for item in items
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Не нашли ответ? Связаться с менеджером",
                    callback_data=MenuCallback(section="manager").pack(),
                )
            ],
            *footer(),
        ]
    )
    await state.clear()
    await message.answer(
        "Результаты поиска:" if items else "Ничего не найдено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(FAQCallback.filter())
async def faq_item(
    callback: CallbackQuery, callback_data: FAQCallback, session: AsyncSession
) -> None:
    item = await session.get(FAQItem, UUID(callback_data.item_id))
    if callback.message:
        await callback.message.edit_text(
            f"<b>{item.question}</b>\n\n{item.answer}" if item else "Ответ не найден.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="← К категориям", callback_data=MenuCallback(section="faq").pack()
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Не нашли ответ? Менеджер",
                            callback_data=MenuCallback(section="manager").pack(),
                        )
                    ],
                ]
            ),
            parse_mode="HTML",
        )
    await callback.answer()
