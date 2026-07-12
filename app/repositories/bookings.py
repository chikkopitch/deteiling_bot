from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, TimeSlot
from app.repositories.base import Repository

ACTIVE = (
    BookingStatus.DRAFT,
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.RESCHEDULE_REQUESTED,
)


class BookingRepository(Repository[Booking]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Booking)

    async def active_for_user(self, user_id: UUID) -> Booking | None:
        return await self.session.scalar(
            select(Booking)
            .where(Booking.user_id == user_id, Booking.status.in_(ACTIVE))
            .order_by(Booking.created_at.desc())
        )

    async def by_idempotency_key(self, key: str) -> Booking | None:
        return await self.session.scalar(select(Booking).where(Booking.idempotency_key == key))

    async def lock(self, booking_id: UUID) -> Booking | None:
        return await self.session.scalar(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )


class SlotRepository(Repository[TimeSlot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TimeSlot)

    async def lock(self, slot_id: UUID) -> TimeSlot | None:
        return await self.session.scalar(
            select(TimeSlot).where(TimeSlot.id == slot_id).with_for_update()
        )
