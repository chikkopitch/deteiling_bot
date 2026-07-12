"""Administrative audit log."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import UUIDPrimaryKeyMixin


class AdminAuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_admin_audit_log_admin_created", "admin_id", "created_at"),
        Index(
            "ix_admin_audit_log_entity_created",
            "entity_type",
            "entity_id",
            "created_at",
        ),
    )

    admin_id: Mapped[UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    old_value: Mapped[dict | list | str | int | None] = mapped_column(JSONB)
    new_value: Mapped[dict | list | str | int | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
