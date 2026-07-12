"""Available slots, reservations, and reminders."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.enums import ReminderStatus, ReservationStatus
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AvailableSlot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "available_slots"
    __table_args__ = (
        UniqueConstraint("starts_at", "ends_at", name="uq_available_slots_time_range"),
        CheckConstraint("ends_at > starts_at", name="time_range_valid"),
        Index("ix_available_slots_available_starts", "is_available", "starts_at"),
    )

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text)


class AppointmentSlotReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointment_slot_reservations"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id", "slot_id", name="uq_reservations_appointment_slot"
        ),
        Index("ix_reservations_status_reserved_until", "status", "reserved_until"),
        Index(
            "uq_reservations_blocking_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'confirmed')"),
        ),
        Index(
            "uq_reservations_blocking_appointment",
            "appointment_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'confirmed')"),
        ),
    )

    appointment_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False
    )
    slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("available_slots.id", ondelete="RESTRICT"), nullable=False
    )
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ReservationStatus] = mapped_column(
        SAEnum(
            ReservationStatus,
            name="reservation_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=ReservationStatus.ACTIVE,
        server_default=ReservationStatus.ACTIVE.value,
    )


class Reminder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id",
            "reminder_type",
            "scheduled_for",
            name="uq_reminders_appointment_type_time",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_reminders_status_scheduled", "status", "scheduled_for"),
    )

    appointment_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False
    )
    reminder_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(
            ReminderStatus,
            name="reminder_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=ReminderStatus.PENDING,
        server_default=ReminderStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
