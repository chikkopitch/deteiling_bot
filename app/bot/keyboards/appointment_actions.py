"""Customer appointment actions and rejection workflow keyboards."""

from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class UserAppointmentCallback(CallbackData, prefix="userapp"):
    action: str
    appointment_id: UUID


class RejectAppointmentCallback(CallbackData, prefix="reject"):
    action: str
    appointment_id: UUID
    reason: str = "-"


TYPICAL_REJECTION_REASONS = {
    "slot": "Выбранное время недоступно",
    "service": "Услуга временно недоступна",
    "contact": "Не удалось связаться с клиентом",
    "capacity": "Нет возможности принять автомобиль",
}


def customer_confirmed_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=UserAppointmentCallback(
                action=action, appointment_id=appointment_id
            ).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("Перенести запись", "reschedule")],
            [button("Отменить запись", "cancel")],
            [button("Связаться с менеджером", "manager")],
        ]
    )


def customer_rejected_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Выбрать новое время",
                    callback_data=UserAppointmentCallback(
                        action="new_booking", appointment_id=appointment_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Связаться с менеджером",
                    callback_data=UserAppointmentCallback(
                        action="manager", appointment_id=appointment_id
                    ).pack(),
                )
            ],
        ]
    )


def rejection_reasons_keyboard(appointment_id: UUID) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=text,
                callback_data=RejectAppointmentCallback(
                    action="preview",
                    appointment_id=appointment_id,
                    reason=code,
                ).pack(),
            )
        ]
        for code, text in TYPICAL_REJECTION_REASONS.items()
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Написать свою причину",
                callback_data=RejectAppointmentCallback(
                    action="custom", appointment_id=appointment_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rejection_confirmation_keyboard(
    appointment_id: UUID, reason_code: str = "custom"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить отклонение",
                    callback_data=RejectAppointmentCallback(
                        action="confirm",
                        appointment_id=appointment_id,
                        reason=reason_code,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=RejectAppointmentCallback(
                        action="abort", appointment_id=appointment_id
                    ).pack(),
                )
            ],
        ]
    )
