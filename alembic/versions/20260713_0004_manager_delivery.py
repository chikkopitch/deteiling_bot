"""add manager message delivery result

Revision ID: 20260713_0004
Revises: 20260713_0003
"""
from alembic import op
import sqlalchemy as sa

revision="20260713_0004"
down_revision="20260713_0003"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("manager_request_messages", sa.Column("delivery_status", sa.String(32), nullable=True))
    op.add_column("manager_request_messages", sa.Column("delivery_error", sa.Text(), nullable=True))
    op.add_column("manager_request_messages", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column("manager_request_messages", "delivered_at")
    op.drop_column("manager_request_messages", "delivery_error")
    op.drop_column("manager_request_messages", "delivery_status")
