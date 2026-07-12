"""Import every ORM model so Alembic can discover complete metadata."""

from app.database.models.accounts import Admin, User
from app.database.models.appointments import (
    Appointment,
    AppointmentHistory,
    AppointmentPhoto,
)
from app.database.models.audit import AdminAuditLog
from app.database.models.catalog import (
    Service,
    ServicePrice,
    VehicleBrand,
    VehicleClass,
    VehicleModel,
)
from app.database.models.content import ContentSetting, FAQItem
from app.database.models.pricing import (
    CalculationFactor,
    CalculationFactorValue,
    PriceCalculation,
    ServiceFactorCompatibility,
)
from app.database.models.conversations import ConversationState
from app.database.models.manager import ManagerRequest, ManagerRequestMessage
from app.database.models.scheduling import (
    AppointmentSlotReservation,
    AvailableSlot,
    Reminder,
)

__all__ = [
    "Admin",
    "AdminAuditLog",
    "Appointment",
    "AppointmentHistory",
    "AppointmentPhoto",
    "AppointmentSlotReservation",
    "AvailableSlot",
    "ContentSetting",
    "ConversationState",
    "FAQItem",
    "CalculationFactor",
    "CalculationFactorValue",
    "ServiceFactorCompatibility",
    "PriceCalculation",
    "ManagerRequest",
    "ManagerRequestMessage",
    "Reminder",
    "Service",
    "ServicePrice",
    "User",
    "VehicleBrand",
    "VehicleClass",
    "VehicleModel",
]
