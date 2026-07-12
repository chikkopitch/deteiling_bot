"""Database-driven preliminary price calculator models."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CalculationFactor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calculation_factors"
    __table_args__ = (
        UniqueConstraint("key", name="uq_calculation_factors_key"),
        Index("ix_calculation_factors_active_sort", "is_active", "sort_order"),
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    input_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="single", server_default="single"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class CalculationFactorValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calculation_factor_values"
    __table_args__ = (
        UniqueConstraint(
            "factor_id", "key", name="uq_calculation_factor_values_factor_key"
        ),
        CheckConstraint(
            "coefficient > 0", name="calculation_factor_value_coefficient_positive"
        ),
        CheckConstraint(
            "fixed_surcharge >= 0",
            name="calculation_factor_value_surcharge_non_negative",
        ),
        Index(
            "ix_calculation_factor_values_factor_active_sort",
            "factor_id",
            "is_active",
            "sort_order",
        ),
    )
    factor_id: Mapped[UUID] = mapped_column(
        ForeignKey("calculation_factors.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    coefficient: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=Decimal("1"), server_default="1"
    )
    fixed_surcharge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class ServiceFactorCompatibility(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_factor_compatibility"
    __table_args__ = (
        UniqueConstraint(
            "service_id", "factor_id", name="uq_service_factor_compatibility"
        ),
    )
    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    factor_id: Mapped[UUID] = mapped_column(
        ForeignKey("calculation_factors.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class PriceCalculation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_calculations"
    __table_args__ = (
        Index("ix_price_calculations_user_created", "user_id", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_class_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle: Mapped[dict] = mapped_column(JSONB, nullable=False)
    selections: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    base_price_from: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_price_to: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    result_price_from: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    result_price_to: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
