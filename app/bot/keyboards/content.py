from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class ContentCallback(CallbackData, prefix="cnt"):
    action: str
    value: str = "-"
    page: int = 0


def services_catalog_keyboard(items, page, pages):
    rows = []
    for item in items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Записаться: {item.name}",
                    callback_data=ContentCallback(
                        action="book", value=str(item.id)
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Рассчитать",
                    callback_data=ContentCallback(
                        action="calc", value=str(item.id)
                    ).pack(),
                ),
            ]
        )
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="←",
                callback_data=ContentCallback(action="services", page=page - 1).pack(),
            )
        )
    if page + 1 < pages:
        nav.append(
            InlineKeyboardButton(
                text="→",
                callback_data=ContentCallback(action="services", page=page + 1).pack(),
            )
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="← Главное меню", callback_data="navigation:main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_categories_keyboard(categories):
    rows = [
        [
            InlineKeyboardButton(
                text=c,
                callback_data=ContentCallback(action="faqcat", value=str(index)).pack(),
            )
        ]
        for index, c in enumerate(categories)
    ]
    rows += [
        [
            InlineKeyboardButton(
                text="Поиск", callback_data=ContentCallback(action="faqsearch").pack()
            )
        ],
        [InlineKeyboardButton(text="← Главное меню", callback_data="navigation:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_items_keyboard(items, category_index, page, pages):
    rows = [
        [
            InlineKeyboardButton(
                text=i.question,
                callback_data=ContentCallback(action="faqitem", value=str(i.id)).pack(),
            )
        ]
        for i in items
    ]
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="←",
                callback_data=ContentCallback(
                    action="faqcat", value=str(category_index), page=page - 1
                ).pack(),
            )
        )
    if page + 1 < pages:
        nav.append(
            InlineKeyboardButton(
                text="→",
                callback_data=ContentCallback(
                    action="faqcat", value=str(category_index), page=page + 1
                ).pack(),
            )
        )
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text="← Категории",
                callback_data=ContentCallback(action="faqroot").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_answer_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Связаться с менеджером",
                    callback_data=ContentCallback(action="manager").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Категории",
                    callback_data=ContentCallback(action="faqroot").pack(),
                )
            ],
        ]
    )
