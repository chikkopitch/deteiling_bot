from sqlalchemy import BigInteger, DateTime, Numeric

from app.database.base import Base
from app.database.enums import AdminRole, ReminderStatus, ReservationStatus
from app.database.models import (  # noqa: F401 - registers all tables
    Admin,
    Appointment,
    ServicePrice,
    User,
)


EXPECTED_TABLES = {
    "users",
    "admins",
    "vehicle_classes",
    "vehicle_brands",
    "vehicle_models",
    "services",
    "service_prices",
    "appointments",
    "appointment_photos",
    "available_slots",
    "appointment_slot_reservations",
    "conversation_states",
    "reminders",
    "faq_items",
    "content_settings",
    "manager_requests",
    "manager_request_messages",
    "appointment_history",
    "admin_audit_log",
    "calculation_factors",
    "calculation_factor_values",
    "service_factor_compatibility",
    "price_calculations",
}


def test_complete_table_set_and_required_types() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert isinstance(User.__table__.c.telegram_id.type, BigInteger)
    assert isinstance(Admin.__table__.c.telegram_id.type, BigInteger)
    assert isinstance(ServicePrice.__table__.c.price.type, Numeric)
    assert isinstance(Appointment.__table__.c.estimated_price_from.type, Numeric)


def test_every_datetime_column_is_timezone_aware() -> None:
    datetime_columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime)
    ]

    assert datetime_columns
    assert all(column.type.timezone for column in datetime_columns)


def test_every_foreign_key_has_explicit_delete_policy() -> None:
    foreign_keys = [
        foreign_key
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_keys
    ]

    assert foreign_keys
    assert all(foreign_key.ondelete for foreign_key in foreign_keys)


def test_required_enums_have_exact_values() -> None:
    assert {role.value for role in AdminRole} == {"owner", "admin", "manager"}
    assert {status.value for status in ReservationStatus} == {
        "active",
        "confirmed",
        "expired",
        "cancelled",
    }
    assert {status.value for status in ReminderStatus} == {
        "pending",
        "processing",
        "sent",
        "failed",
        "cancelled",
    }
