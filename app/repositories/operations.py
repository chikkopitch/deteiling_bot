from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BookingPhoto, StudioSchedule, TimeSlot
from app.models.enums import SlotStatus
from app.repositories.base import Repository


class ScheduleRepository(Repository[StudioSchedule]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudioSchedule)

    async def for_weekday(self, weekday: int) -> list[StudioSchedule]:
        return list(
            await self.session.scalars(
                select(StudioSchedule)
                .where(StudioSchedule.weekday == weekday)
                .order_by(StudioSchedule.effective_date.desc())
            )
        )


class PhotoRepository(Repository[BookingPhoto]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BookingPhoto)

    async def for_booking(self, booking_id: UUID) -> list[BookingPhoto]:
        return list(
            await self.session.scalars(
                select(BookingPhoto)
                .where(BookingPhoto.booking_id == booking_id)
                .order_by(BookingPhoto.sort_order)
            )
        )


class AuditLogRepository(Repository[AuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditLog)

    async def for_entity(self, entity_type: str, entity_id: UUID) -> list[AuditLog]:
        return list(
            await self.session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
                .order_by(AuditLog.created_at.desc())
            )
        )


class AvailabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def available_after(self, moment: datetime, limit: int = 100) -> list[TimeSlot]:
        return list(
            await self.session.scalars(
                select(TimeSlot)
                .where(TimeSlot.starts_at >= moment, TimeSlot.status == SlotStatus.AVAILABLE)
                .order_by(TimeSlot.starts_at)
                .limit(limit)
            )
        )
