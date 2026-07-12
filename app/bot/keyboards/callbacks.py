from aiogram.filters.callback_data import CallbackData


class MenuCallback(CallbackData, prefix="menu"):
    section: str


class BookingCallback(CallbackData, prefix="book"):
    action: str
    value: str = "-"


class AdminCallback(CallbackData, prefix="adm"):
    action: str
    entity_id: str = "-"
    value: str = "-"


class PageCallback(CallbackData, prefix="page"):
    section: str
    page: int


class FAQCallback(CallbackData, prefix="faq"):
    item_id: str


class ServiceCallback(CallbackData, prefix="service"):
    item_id: str


class FAQCategoryCallback(CallbackData, prefix="faqcat"):
    category: str


class CatalogCallback(CallbackData, prefix="catalog"):
    action: str
    value: str = "-"
