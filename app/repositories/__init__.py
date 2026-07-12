from app.repositories.bookings import BookingRepository, SlotRepository
from app.repositories.catalog import CatalogRepository, ServiceRepository
from app.repositories.content import (
    FAQRepository,
    ManagerRequestRepository,
    ServiceCategoryRepository,
)
from app.repositories.notifications import NotificationRepository
from app.repositories.operations import (
    AuditLogRepository,
    AvailabilityRepository,
    PhotoRepository,
    ScheduleRepository,
)
from app.repositories.users import UserRepository
from app.repositories.vehicles import (
    VehicleBrandRepository,
    VehicleModelRepository,
    VehicleRepository,
)

__all__ = [
    "BookingRepository",
    "AuditLogRepository",
    "AvailabilityRepository",
    "CatalogRepository",
    "FAQRepository",
    "ManagerRequestRepository",
    "NotificationRepository",
    "PhotoRepository",
    "ScheduleRepository",
    "ServiceCategoryRepository",
    "ServiceRepository",
    "SlotRepository",
    "UserRepository",
    "VehicleBrandRepository",
    "VehicleModelRepository",
    "VehicleRepository",
]
