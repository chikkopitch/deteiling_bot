"""FAQ and editable content models."""

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FAQItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "faq_items"
    __table_args__ = (
        Index(
            "ix_faq_items_active_category_sort", "is_active", "category", "sort_order"
        ),
    )

    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class ContentSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_content_settings_key"),)

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
