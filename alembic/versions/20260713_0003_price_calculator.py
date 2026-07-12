"""add database-driven price calculator

Revision ID: 20260713_0003
Revises: 20260712_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260713_0003"
down_revision = "20260712_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("faq_items", sa.Column("keywords", sa.Text(), nullable=True))
    op.create_table("calculation_factors",
        sa.Column("key", sa.String(80), nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("input_type", sa.String(20), server_default="single", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("key", name="uq_calculation_factors_key"))
    op.create_index("ix_calculation_factors_active_sort", "calculation_factors", ["is_active", "sort_order"])
    op.create_table("calculation_factor_values",
        sa.Column("factor_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False), sa.Column("coefficient", sa.Numeric(8,4), server_default="1", nullable=False),
        sa.Column("fixed_surcharge", sa.Numeric(12,2), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False), sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("coefficient > 0", name="calculation_factor_value_coefficient_positive"), sa.CheckConstraint("fixed_surcharge >= 0", name="calculation_factor_value_surcharge_non_negative"),
        sa.ForeignKeyConstraint(["factor_id"], ["calculation_factors.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("factor_id", "key", name="uq_calculation_factor_values_factor_key"))
    op.create_index("ix_calculation_factor_values_factor_active_sort", "calculation_factor_values", ["factor_id", "is_active", "sort_order"])
    op.create_table("service_factor_compatibility",
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("factor_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["factor_id"], ["calculation_factors.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("service_id", "factor_id", name="uq_service_factor_compatibility"))
    op.create_table("price_calculations",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("vehicle_class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle", postgresql.JSONB(), nullable=False), sa.Column("selections", postgresql.JSONB(), nullable=False),
        sa.Column("base_price_from", sa.Numeric(12,2), nullable=False), sa.Column("base_price_to", sa.Numeric(12,2), nullable=False), sa.Column("result_price_from", sa.Numeric(12,2), nullable=False), sa.Column("result_price_to", sa.Numeric(12,2), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["vehicle_class_id"], ["vehicle_classes.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_price_calculations_user_created", "price_calculations", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_price_calculations_user_created", table_name="price_calculations")
    op.drop_table("price_calculations")
    op.drop_table("service_factor_compatibility")
    op.drop_index("ix_calculation_factor_values_factor_active_sort", table_name="calculation_factor_values")
    op.drop_table("calculation_factor_values")
    op.drop_index("ix_calculation_factors_active_sort", table_name="calculation_factors")
    op.drop_table("calculation_factors")
    op.drop_column("faq_items", "keywords")
