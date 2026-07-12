from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationStatus
from app.repositories.base import Repository


class NotificationRepository(Repository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Notification)

    async def due(self, now: datetime, limit: int = 50) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.status.in_((NotificationStatus.PENDING, NotificationStatus.RETRY)),
                Notification.scheduled_at <= now,
            )
            .order_by(Notification.scheduled_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(await self.session.scalars(stmt))

    async def by_idempotency_key(self, key: str) -> Notification | None:
        return await self.session.scalar(
            select(Notification).where(Notification.idempotency_key == key)
        )

    async def cancel_pending_for_booking(self, booking_id: UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.booking_id == booking_id,
                Notification.status.in_((NotificationStatus.PENDING, NotificationStatus.RETRY)),
            )
            .values(status=NotificationStatus.CANCELLED)
        )
