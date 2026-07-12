"""Persistent conversation state model."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ConversationState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_states"
    __table_args__ = (
        # The row is reused/upserted after expiry, so this enforces at most one
        # current state per user and flow without a volatile partial index.
        UniqueConstraint("user_id", "flow", name="uq_conversation_states_user_flow"),
        Index("ix_conversation_states_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    flow: Mapped[str] = mapped_column(String(64), nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
