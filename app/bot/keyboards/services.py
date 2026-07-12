"""Service selection and photo upload keyboards."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.service_selection import ServicePage


class ServiceCallback(CallbackData, prefix="svc"):
    flow: str
    action: str
    value: str = "-"


class PhotoCallback(CallbackData, prefix="photo"):
    action: str


def _service_callback(flow: str, action: str, value: str = "-") -> str:
    return ServiceCallback(flow=flow, action=action, value=value).pack()


def services_keyboard(flow: str, page: ServicePage) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Выбрать: {card.service.name}",
                callback_data=_service_callback(flow, "select", str(card.service.id)),
            )
        ]
        for card in page.cards
    ]
    if page.pages > 1:
        pagination: list[InlineKeyboardButton] = []
        if page.page > 0:
            pagination.append(
                InlineKeyboardButton(
                    text="←",
                    callback_data=_service_callback(flow, "page", str(page.page - 1)),
                )
            )
        pagination.append(
            InlineKeyboardButton(
                text=f"{page.page + 1}/{page.pages}", callback_data="noop"
            )
        )
        if page.page + 1 < page.pages:
            pagination.append(
                InlineKeyboardButton(
                    text="→",
                    callback_data=_service_callback(flow, "page", str(page.page + 1)),
                )
            )
        rows.append(pagination)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Бесплатный осмотр",
                    callback_data=_service_callback(flow, "free"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Не знаю, нужна консультация",
                    callback_data=_service_callback(flow, "consult"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=_service_callback(flow, "back"),
                ),
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=_service_callback(flow, "cancel"),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Готово",
                    callback_data=PhotoCallback(action="done").pack(),
                ),
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data=PhotoCallback(action="skip").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Удалить последнее фото",
                    callback_data=PhotoCallback(action="remove").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=PhotoCallback(action="back").pack(),
                ),
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=PhotoCallback(action="cancel").pack(),
                ),
            ],
        ]
    )
