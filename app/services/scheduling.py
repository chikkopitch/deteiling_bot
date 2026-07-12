from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SlotStatus, StudioSchedule, TimeSlot
from app.utils.datetime import utc_now


class AvailabilityService:
    def __init__(self, session: AsyncSession, timezone: str) -> None:
        self.session = session
        self.timezone = ZoneInfo(timezone)

    async def release_expired_holds(self) -> int:
        result = await self.session.execute(
            update(TimeSlot)
            .where(
                TimeSlot.status == SlotStatus.HELD,
                TimeSlot.hold_expires_at.is_not(None),
                TimeSlot.hold_expires_at <= utc_now(),
            )
            .values(status=SlotStatus.AVAILABLE, held_by_user_id=None, hold_expires_at=None)
        )
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def dates_for_week(
        self, week_offset: int, horizon_days: int, user_id: UUID | None = None
    ) -> list[date]:
        today = utc_now().astimezone(self.timezone).date()
        start = today + timedelta(days=week_offset * 7)
        end = min(start + timedelta(days=7), today + timedelta(days=horizon_days + 1))
        if start >= end:
            return []
        slots = await self._slots_between(
            datetime.combine(start, time.min, self.timezone).astimezone(UTC),
            datetime.combine(end, time.min, self.timezone).astimezone(UTC),
            user_id,
        )
        return sorted({slot.starts_at.astimezone(self.timezone).date() for slot in slots})

    async def slots_for_date(self, target: date, user_id: UUID | None = None) -> list[TimeSlot]:
        start = datetime.combine(target, time.min, self.timezone).astimezone(UTC)
        end = start + timedelta(days=1)
        return await self._slots_between(start, end, user_id)

    async def _slots_between(
        self, start: datetime, end: datetime, user_id: UUID | None
    ) -> list[TimeSlot]:
        availability_condition = TimeSlot.status == SlotStatus.AVAILABLE
        if user_id is not None:
            availability_condition = or_(
                availability_condition,
                and_(
                    TimeSlot.status == SlotStatus.HELD,
                    TimeSlot.held_by_user_id == user_id,
                    TimeSlot.hold_expires_at > utc_now(),
                ),
            )
        statement = (
            select(TimeSlot)
            .where(TimeSlot.starts_at >= start, TimeSlot.starts_at < end, availability_condition)
            .order_by(TimeSlot.starts_at)
        )
        slots = list(await self.session.scalars(statement))
        return await self._filter_by_schedule(slots)

    async def _filter_by_schedule(self, slots: list[TimeSlot]) -> list[TimeSlot]:
        if not slots:
            return []
        local_dates = {slot.starts_at.astimezone(self.timezone).date() for slot in slots}
        schedules = list(
            await self.session.scalars(
                select(StudioSchedule).where(
                    or_(
                        StudioSchedule.effective_date.in_(local_dates),
                        StudioSchedule.effective_date.is_(None),
                    )
                )
            )
        )
        if not schedules:
            return slots
        by_date = {rule.effective_date: rule for rule in schedules if rule.effective_date}
        by_weekday = {rule.weekday: rule for rule in schedules if rule.effective_date is None}
        filtered: list[TimeSlot] = []
        for slot in slots:
            local_start = slot.starts_at.astimezone(self.timezone)
            local_end = slot.ends_at.astimezone(self.timezone)
            rule = by_date.get(local_start.date()) or by_weekday.get(local_start.weekday())
            if rule is None or rule.is_closed:
                continue
            if local_start.time() < rule.opens_at or local_end.time() > rule.closes_at:
                continue
            if any(
                self._overlaps_break(local_start.time(), local_end.time(), item)
                for item in rule.breaks
            ):
                continue
            filtered.append(slot)
        return filtered

    @staticmethod
    def _overlaps_break(start: time, end: time, interval: dict[str, str]) -> bool:
        try:
            break_start = time.fromisoformat(interval["start"])
            break_end = time.fromisoformat(interval["end"])
        except (KeyError, ValueError):
            return False
        return start < break_end and end > break_start
