"""Appointment, photo, and status history models."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.enums import AppointmentStatus, MediaType
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "vehicle_year IS NULL OR (vehicle_year > 0 AND vehicle_year <= 9999)",
            name="vehicle_year_valid",
        ),
        CheckConstraint(
            "estimated_price_from IS NULL OR estimated_price_from >= 0",
            name="estimated_price_from_non_negative",
        ),
        CheckConstraint(
            "estimated_price_to IS NULL OR estimated_price_to >= 0",
            name="estimated_price_to_non_negative",
        ),
        CheckConstraint(
            "estimated_price_from IS NULL OR estimated_price_to IS NULL "
            "OR estimated_price_from <= estimated_price_to",
            name="estimated_price_range_valid",
        ),
        Index("ix_appointments_user_status", "user_id", "status"),
        Index("ix_appointments_status_scheduled_at", "status", "scheduled_at"),
        Index("ix_appointments_slot_id", "slot_id"),
        Index("ix_appointments_service_id", "service_id"),
        Index("ix_appointments_vehicle_brand_id", "vehicle_brand_id"),
        Index("ix_appointments_vehicle_model_id", "vehicle_model_id"),
        Index("ix_appointments_vehicle_class_id", "vehicle_class_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    service_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT")
    )
    vehicle_brand_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vehicle_brands.id", ondelete="RESTRICT")
    )
    vehicle_model_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vehicle_models.id", ondelete="RESTRICT")
    )
    vehicle_class_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="RESTRICT")
    )
    custom_vehicle_brand: Mapped[str | None] = mapped_column(String(120))
    custom_vehicle_model: Mapped[str | None] = mapped_column(String(120))
    vehicle_year: Mapped[int | None] = mapped_column(Integer)
    vehicle_comment: Mapped[str | None] = mapped_column(Text)
    customer_name: Mapped[str | None] = mapped_column(String(120))
    customer_phone: Mapped[str | None] = mapped_column(String(32))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    slot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("available_slots.id", ondelete="RESTRICT")
    )
    estimated_price_from: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    estimated_price_to: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            AppointmentStatus,
            name="appointment_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=AppointmentStatus.DRAFT,
        server_default=AppointmentStatus.DRAFT.value,
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    confirmed_by_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppointmentPhoto(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "appointment_photos"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id",
            "telegram_file_unique_id",
            name="uq_appointment_photos_appointment_file",
        ),
        Index("ix_appointment_photos_appointment_id", "appointment_id"),
    )

    appointment_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    telegram_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    telegram_file_unique_id: Mapped[str] = mapped_column(String(256), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(
        SAEnum(
            MediaType, name="media_type", values_callable=lambda e: [x.value for x in e]
        ),
        nullable=False,
        default=MediaType.PHOTO,
        server_default=MediaType.PHOTO.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AppointmentHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "appointment_history"
    __table_args__ = (
        Index(
            "ix_appointment_history_appointment_created", "appointment_id", "created_at"
        ),
        Index("ix_appointment_history_changed_by_admin", "changed_by_admin_id"),
    )

    appointment_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[dict | list | str | int | None] = mapped_column(JSONB)
    new_value: Mapped[dict | list | str | int | None] = mapped_column(JSONB)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    changed_by_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
