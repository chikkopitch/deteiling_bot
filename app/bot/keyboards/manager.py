from uuid import UUID
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

TOPICS = {
    "price": "Стоимость",
    "service": "Услуга",
    "change": "Изменение записи",
    "corporate": "Корпоративное обслуживание",
    "other": "Другое",
}


class ManagerUserCallback(CallbackData, prefix="mru"):
    action: str
    value: str = "-"


class ManagerAdminCallback(CallbackData, prefix="mra"):
    action: str
    request_id: UUID


def topics_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=v,
                    callback_data=ManagerUserCallback(action="topic", value=k).pack(),
                )
            ]
            for k, v in TOPICS.items()
        ]
        + [
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=ManagerUserCallback(action="cancel").pack(),
                )
            ]
        ]
    )


def photos_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Готово",
                    callback_data=ManagerUserCallback(action="review").pack(),
                ),
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data=ManagerUserCallback(action="review").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=ManagerUserCallback(action="cancel").pack(),
                )
            ],
        ]
    )


def review_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить",
                    callback_data=ManagerUserCallback(action="submit").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить",
                    callback_data=ManagerUserCallback(action="restart").pack(),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=ManagerUserCallback(action="cancel").pack(),
                ),
            ],
        ]
    )


def manager_request_keyboard(request_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть",
                    callback_data=ManagerAdminCallback(
                        action="open", request_id=request_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назначить себе",
                    callback_data=ManagerAdminCallback(
                        action="assign", request_id=request_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Ответить",
                    callback_data=ManagerAdminCallback(
                        action="reply", request_id=request_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=ManagerAdminCallback(
                        action="close", request_id=request_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Переоткрыть",
                    callback_data=ManagerAdminCallback(
                        action="reopen", request_id=request_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Передать",
                    callback_data=ManagerAdminCallback(
                        action="transfer", request_id=request_id
                    ).pack(),
                )
            ],
        ]
    )
