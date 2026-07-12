"""Add selected slot reference to appointments.

Revision ID: 20260712_0002
Revises: 20260712_0001
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260712_0002"
down_revision: str | None = "20260712_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("slot_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointments_slot_id_available_slots",
        "appointments",
        "available_slots",
        ["slot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_appointments_slot_id", "appointments", ["slot_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_slot_id", table_name="appointments")
    op.drop_constraint(
        "fk_appointments_slot_id_available_slots",
        "appointments",
        type_="foreignkey",
    )
    op.drop_column("appointments", "slot_id")
