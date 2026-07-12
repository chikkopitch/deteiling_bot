"""Manager request and message models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.enums import ManagerRequestStatus, SenderType
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ManagerRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manager_requests"
    __table_args__ = (
        Index("ix_manager_requests_status_created", "status", "created_at"),
        Index("ix_manager_requests_user_id", "user_id"),
        Index("ix_manager_requests_appointment_id", "appointment_id"),
        Index("ix_manager_requests_assigned_admin_id", "assigned_admin_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT")
    )
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ManagerRequestStatus] = mapped_column(
        SAEnum(
            ManagerRequestStatus,
            name="manager_request_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=ManagerRequestStatus.OPEN,
        server_default=ManagerRequestStatus.OPEN.value,
    )
    assigned_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManagerRequestMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "manager_request_messages"
    __table_args__ = (
        Index(
            "ix_manager_request_messages_request_created", "request_id", "created_at"
        ),
    )

    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("manager_requests.id", ondelete="RESTRICT"), nullable=False
    )
    sender_type: Mapped[SenderType] = mapped_column(
        SAEnum(
            SenderType,
            name="sender_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    sender_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    sender_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    text: Mapped[str | None] = mapped_column(Text)
    telegram_file_id: Mapped[str | None] = mapped_column(String(512))
    delivery_status: Mapped[str | None] = mapped_column(String(32))
    delivery_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
