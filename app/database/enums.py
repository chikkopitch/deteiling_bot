"""Database-backed domain enumerations."""

from enum import StrEnum


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"


class AppointmentStatus(StrEnum):
    DRAFT = "draft"
    WAITING_ADMIN = "waiting_admin"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED_BY_USER = "cancelled_by_user"
    CANCELLED_BY_ADMIN = "cancelled_by_admin"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManagerRequestStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_MANAGER = "waiting_manager"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class SenderType(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class MediaType(StrEnum):
    PHOTO = "photo"
    DOCUMENT = "document"
