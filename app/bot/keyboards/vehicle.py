"""Vehicle selection callback schema and paginated inline keyboards."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import VehicleBrand, VehicleClass, VehicleModel
from app.services.vehicle_selection import Page


class VehicleCallback(CallbackData, prefix="veh"):
    flow: str
    entity: str
    action: str
    value: str = "-"


def _callback(flow: str, entity: str, action: str, value: str = "-") -> str:
    return VehicleCallback(flow=flow, entity=entity, action=action, value=value).pack()


def _pagination_rows(
    flow: str, entity: str, page: int, pages: int
) -> list[list[InlineKeyboardButton]]:
    if pages <= 1:
        return []
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="←",
                callback_data=_callback(flow, entity, "page", str(page - 1)),
            )
        )
    row.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page + 1 < pages:
        row.append(
            InlineKeyboardButton(
                text="→",
                callback_data=_callback(flow, entity, "page", str(page + 1)),
            )
        )
    return [row]


def brands_keyboard(flow: str, page: Page) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=item.name,
                callback_data=_callback(flow, "br", "select", str(item.id)),
            )
        ]
        for item in page.items
        if isinstance(item, VehicleBrand)
    ]
    rows.extend(_pagination_rows(flow, "br", page.page, page.pages))
    rows.append(
        [
            InlineKeyboardButton(
                text="🔎 Поиск", callback_data=_callback(flow, "br", "search")
            ),
            InlineKeyboardButton(
                text="Другая марка", callback_data=_callback(flow, "br", "custom")
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="← Назад", callback_data=_callback(flow, "flow", "back")
            ),
            InlineKeyboardButton(
                text="Отменить", callback_data=_callback(flow, "flow", "cancel")
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def models_keyboard(flow: str, page: Page) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=item.name,
                callback_data=_callback(flow, "mo", "select", str(item.id)),
            )
        ]
        for item in page.items
        if isinstance(item, VehicleModel)
    ]
    rows.extend(_pagination_rows(flow, "mo", page.page, page.pages))
    rows.append(
        [
            InlineKeyboardButton(
                text="🔎 Поиск", callback_data=_callback(flow, "mo", "search")
            ),
            InlineKeyboardButton(
                text="Другая модель", callback_data=_callback(flow, "mo", "custom")
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="← К маркам", callback_data=_callback(flow, "mo", "back")
            ),
            InlineKeyboardButton(
                text="Отменить", callback_data=_callback(flow, "flow", "cancel")
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def classes_keyboard(flow: str, classes: list[VehicleClass]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=item.name,
                callback_data=_callback(flow, "cl", "select", str(item.id)),
            )
        ]
        for item in classes
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← Назад", callback_data=_callback(flow, "cl", "back")
            ),
            InlineKeyboardButton(
                text="Отменить", callback_data=_callback(flow, "flow", "cancel")
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_input_keyboard(flow: str, entity: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data=_callback(flow, entity, "back")
                ),
                InlineKeyboardButton(
                    text="Отменить", callback_data=_callback(flow, "flow", "cancel")
                ),
            ]
        ]
    )


def year_keyboard(flow: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить", callback_data=_callback(flow, "yr", "skip")
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data=_callback(flow, "yr", "back")
                ),
                InlineKeyboardButton(
                    text="Отменить", callback_data=_callback(flow, "flow", "cancel")
                ),
            ],
        ]
    )
