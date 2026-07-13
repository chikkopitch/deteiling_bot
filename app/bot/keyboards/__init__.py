"""Telegram keyboard builders."""

from app.bot.keyboards.drafts import DraftActionCallback, draft_recovery_keyboard
from app.bot.keyboards.main_menu import back_to_menu_keyboard, main_menu_keyboard
from app.bot.keyboards.vehicle import VehicleCallback
from app.bot.keyboards.services import ServiceCallback
from app.bot.keyboards.schedule import ScheduleCallback
from app.bot.keyboards.contacts import ContactCallback, ReviewCallback
from app.bot.keyboards.admin import (
    AdminApplicationCallback,
    AdminChangeCallback,
    AdminPanelCallback,
)
from app.bot.keyboards.appointment_actions import (
    RejectAppointmentCallback,
    UserAppointmentCallback,
)
from app.bot.keyboards.my_appointments import MyAppointmentCallback
from app.bot.keyboards.calculator import CalculatorCallback

__all__ = [
    "DraftActionCallback",
    "VehicleCallback",
    "ServiceCallback",
    "ScheduleCallback",
    "ContactCallback",
    "ReviewCallback",
    "AdminApplicationCallback",
    "AdminChangeCallback",
    "AdminPanelCallback",
    "RejectAppointmentCallback",
    "UserAppointmentCallback",
    "MyAppointmentCallback",
    "CalculatorCallback",
    "back_to_menu_keyboard",
    "draft_recovery_keyboard",
    "main_menu_keyboard",
]
