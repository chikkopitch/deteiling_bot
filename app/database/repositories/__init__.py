"""Repository public API."""

from app.database.repositories.accounts import AdminRepository, UserRepository
from app.database.repositories.appointments import (
    AppointmentRepository,
    AvailableSlotRepository,
    ReservationRepository,
)
from app.database.repositories.catalog import (
    ServiceRepository,
    VehicleBrandRepository,
    VehicleClassRepository,
    VehicleModelRepository,
)
from app.database.repositories.conversations import ConversationStateRepository
from app.database.repositories.content import ContentSettingRepository, FAQRepository
from app.database.repositories.operations import (
    AdminAuditLogRepository,
    AppointmentHistoryRepository,
    ManagerRequestRepository,
    ReminderRepository,
)
from app.database.repositories.photos import AppointmentPhotoRepository

__all__ = [
    "AdminRepository",
    "AdminAuditLogRepository",
    "AppointmentHistoryRepository",
    "AppointmentPhotoRepository",
    "AppointmentRepository",
    "AvailableSlotRepository",
    "ContentSettingRepository",
    "ConversationStateRepository",
    "FAQRepository",
    "ManagerRequestRepository",
    "ReminderRepository",
    "ReservationRepository",
    "ServiceRepository",
    "UserRepository",
    "VehicleBrandRepository",
    "VehicleClassRepository",
    "VehicleModelRepository",
]
