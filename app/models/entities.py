from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    BookingStatus,
    ManagerRequestStatus,
    NotificationStatus,
    NotificationType,
    SlotStatus,
    UserRole,
)

booking_services = Table(
    "booking_services",
    Base.metadata,
    Column("booking_id", ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="RESTRICT"), primary_key=True),
)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.CLIENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class VehicleBrand(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_brands"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    models: Mapped[list["VehicleModel"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )


class VehicleModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_models"
    __table_args__ = (UniqueConstraint("brand_id", "name"),)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle_brands.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    brand: Mapped[VehicleBrand] = relationship(back_populates="models")


class Vehicle(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (CheckConstraint("year >= 1980 AND year <= 2200", name="valid_year"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    brand_name: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(100))
    year: Mapped[int] = mapped_column(Integer)
    vehicle_class: Mapped[str] = mapped_column(String(32))


class ServiceCategory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "service_categories"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    services: Mapped[list["Service"]] = relationship(back_populates="category")


class Service(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (CheckConstraint("price_from >= 0", name="nonnegative_price"),)
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("service_categories.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    short_description: Mapped[str] = mapped_column(Text)
    includes: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_from: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    suitable_for: Mapped[str] = mapped_column(Text, default="Все автомобили")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[ServiceCategory] = relationship(back_populates="services", lazy="selectin")


class PriceRule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "price_rules"
    __table_args__ = (
        CheckConstraint("min_price >= 0 AND max_price >= min_price", name="valid_price_range"),
    )
    service_id: Mapped[UUID] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    vehicle_class: Mapped[str] = mapped_column(String(32))
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    class_coefficient: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=1)
    condition_coefficients: Mapped[dict[str, float]] = mapped_column(JSON)
    options: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    min_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    max_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StudioSchedule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "studio_schedules"
    __table_args__ = (UniqueConstraint("weekday", "effective_date"),)
    weekday: Mapped[int] = mapped_column(Integer)
    opens_at: Mapped[time] = mapped_column(Time)
    closes_at: Mapped[time] = mapped_column(Time)
    breaks: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    effective_date: Mapped[date | None] = mapped_column(Date)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=60)


class TimeSlot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "time_slots"
    __table_args__ = (
        UniqueConstraint("starts_at"),
        CheckConstraint("ends_at > starts_at", name="positive_duration"),
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[SlotStatus] = mapped_column(Enum(SlotStatus), default=SlotStatus.AVAILABLE)
    held_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Booking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "uq_active_booking_slot",
            "slot_id",
            unique=True,
            postgresql_where=text(
                "status IN ('DRAFT', 'PENDING', 'CONFIRMED', 'RESCHEDULE_REQUESTED')"
            ),
            sqlite_where=text(
                "status IN ('DRAFT', 'PENDING', 'CONFIRMED', 'RESCHEDULE_REQUESTED')"
            ),
        ),
        CheckConstraint(
            "estimated_min IS NULL OR estimated_max IS NULL OR estimated_max >= estimated_min",
            name="valid_estimate_range",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    vehicle_id: Mapped[UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    slot_id: Mapped[UUID | None] = mapped_column(ForeignKey("time_slots.id", ondelete="SET NULL"))
    proposed_slot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("time_slots.id", ondelete="SET NULL")
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), default=BookingStatus.DRAFT, index=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(80))
    customer_phone: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    estimated_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    estimated_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    services: Mapped[list[Service]] = relationship(secondary=booking_services, lazy="selectin")
    slot: Mapped[TimeSlot | None] = relationship(lazy="selectin", foreign_keys=[slot_id])
    vehicle: Mapped[Vehicle] = relationship(lazy="selectin")


class BookingPhoto(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "booking_photos"
    __table_args__ = (
        UniqueConstraint("booking_id", "unique_file_id"),
        UniqueConstraint("booking_id", "sort_order"),
        CheckConstraint("size_bytes >= 0", name="nonnegative_size"),
    )
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    file_id: Mapped[str] = mapped_column(String(255))
    unique_file_id: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sort_order: Mapped[int] = mapped_column(Integer)


class FAQItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "faq_items"
    category: Mapped[str] = mapped_column(String(80))
    question: Mapped[str] = mapped_column(String(255))
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManagerRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "manager_requests"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    text: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(String(20))
    photo_file_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[ManagerRequestStatus] = mapped_column(
        Enum(ManagerRequestStatus), default=ManagerRequestStatus.OPEN
    )
    response: Mapped[str | None] = mapped_column(Text)


class Notification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus), default=NotificationStatus.PENDING, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(150), unique=True)


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID | None]
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
