"""Customer and staff account models."""

from sqlalchemy import BigInteger, Boolean, Enum as SAEnum, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.enums import AdminRole
from app.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_telegram_id", "telegram_id", unique=True),)

    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))
    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )


class Admin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admins"
    __table_args__ = (
        Index("ix_admins_telegram_id", "telegram_id", unique=True),
        Index("ix_admins_role_is_active", "role", "is_active"),
    )

    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        SAEnum(
            AdminRole, name="admin_role", values_callable=lambda e: [x.value for x in e]
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
