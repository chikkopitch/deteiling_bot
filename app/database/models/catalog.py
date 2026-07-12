"""Vehicle catalog, services, and class-specific prices."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VehicleClass(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_classes"
    __table_args__ = (
        UniqueConstraint("name", name="uq_vehicle_classes_name"),
        CheckConstraint("price_coefficient > 0", name="price_coefficient_positive"),
        Index("ix_vehicle_classes_active_sort", "is_active", "sort_order"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_coefficient: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("1.0000"),
        server_default=text("1.0000"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class VehicleBrand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_brands"
    __table_args__ = (
        UniqueConstraint("name", name="uq_vehicle_brands_name"),
        Index("ix_vehicle_brands_active_sort", "is_active", "sort_order"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class VehicleModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_models"
    __table_args__ = (
        UniqueConstraint("brand_id", "name", name="uq_vehicle_models_brand_name"),
        Index(
            "ix_vehicle_models_brand_active_sort", "brand_id", "is_active", "sort_order"
        ),
        Index("ix_vehicle_models_vehicle_class_id", "vehicle_class_id"),
    )

    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicle_brands.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_class_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class Service(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("name", name="uq_services_name"),
        CheckConstraint("base_price >= 0", name="base_price_non_negative"),
        CheckConstraint("duration_minutes > 0", name="duration_minutes_positive"),
        Index("ix_services_active_sort", "is_active", "sort_order"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(500))
    full_description: Mapped[str | None] = mapped_column(Text)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_free_inspection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class ServicePrice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_prices"
    __table_args__ = (
        UniqueConstraint(
            "service_id", "vehicle_class_id", name="uq_service_prices_service_class"
        ),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint(
            "min_price IS NULL OR min_price >= 0", name="min_price_non_negative"
        ),
        CheckConstraint(
            "max_price IS NULL OR max_price >= 0", name="max_price_non_negative"
        ),
        CheckConstraint(
            "min_price IS NULL OR max_price IS NULL OR min_price <= max_price",
            name="price_range_valid",
        ),
        Index("ix_service_prices_vehicle_class_id", "vehicle_class_id"),
    )

    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_class_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="RESTRICT"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
