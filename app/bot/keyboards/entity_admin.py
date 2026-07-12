from uuid import UUID
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class EntityAdminCallback(CallbackData, prefix="aed"):
    action: str
    entity: str
    entity_id: UUID


def entity_list_keyboard(entity, items):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=getattr(item, "name", None)
                    or getattr(item, "question", None)
                    or str(item.id)[:8],
                    callback_data=EntityAdminCallback(
                        action="edit", entity=entity, entity_id=item.id
                    ).pack(),
                )
            ]
            for item in items
        ]
    )


def entity_preview_keyboard(entity, entity_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сохранить",
                    callback_data=EntityAdminCallback(
                        action="save", entity=entity, entity_id=entity_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить",
                    callback_data=EntityAdminCallback(
                        action="edit", entity=entity, entity_id=entity_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=EntityAdminCallback(
                        action="cancel", entity=entity, entity_id=entity_id
                    ).pack(),
                ),
            ],
        ]
    )
