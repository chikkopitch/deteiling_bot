"""Administrative creation and closure of customer-facing booking slots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import ReservationStatus
from app.database.models import (
    Admin,
    AdminAuditLog,
    AppointmentSlotReservation,
    AvailableSlot,
)


MAX_SLOTS_PER_REQUEST = 30
MIN_SLOT_DURATION_MINUTES = 5
MAX_SLOT_DURATION_MINUTES = 720


class AdminScheduleError(ValueError):
    """Raised when an admin schedule change is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class SlotDraft:
    starts_at: datetime
    ends_at: datetime


def parse_slot_drafts(
    text: str,
    *,
    timezone: ZoneInfo,
    booking_days_ahead: int,
    now: datetime | None = None,
) -> list[SlotDraft]:
    """Parse local-time lines in ``DD.MM.YYYY HH:MM DURATION_MINUTES`` format."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise AdminScheduleError("Введите хотя бы один слот.")
    if len(lines) > MAX_SLOTS_PER_REQUEST:
        raise AdminScheduleError(
            f"За один раз можно добавить не более {MAX_SLOTS_PER_REQUEST} слотов."
        )

    current = (now or datetime.now(UTC)).astimezone(timezone)
    maximum_date = current.date() + timedelta(days=booking_days_ahead)
    drafts: list[SlotDraft] = []
    for line_number, line in enumerate(lines, start=1):
        parts = line.split()
        if len(parts) != 3:
            raise AdminScheduleError(
                f"Строка {line_number}: используйте формат ДД.ММ.ГГГГ ЧЧ:ММ ДЛИТЕЛЬНОСТЬ."
            )
        try:
            starts_at = datetime.strptime(
                f"{parts[0]} {parts[1]}", "%d.%m.%Y %H:%M"
            ).replace(tzinfo=timezone)
            duration_minutes = int(parts[2])
        except ValueError as error:
            raise AdminScheduleError(
                f"Строка {line_number}: дата, время или длительность указаны неверно."
            ) from error
        if not MIN_SLOT_DURATION_MINUTES <= duration_minutes <= MAX_SLOT_DURATION_MINUTES:
            raise AdminScheduleError(
                f"Строка {line_number}: длительность — от "
                f"{MIN_SLOT_DURATION_MINUTES} до {MAX_SLOT_DURATION_MINUTES} минут."
            )
        if starts_at <= current:
            raise AdminScheduleError(f"Строка {line_number}: время уже прошло.")
        if starts_at.date() > maximum_date:
            raise AdminScheduleError(
                f"Строка {line_number}: дата за пределами окна записи ({booking_days_ahead} дней)."
            )
        draft = SlotDraft(
            starts_at=starts_at.astimezone(UTC),
            ends_at=(starts_at + timedelta(minutes=duration_minutes)).astimezone(UTC),
        )
        if any(
            draft.starts_at < item.ends_at and draft.ends_at > item.starts_at
            for item in drafts
        ):
            raise AdminScheduleError(
                f"Строка {line_number}: слоты из сообщения пересекаются."
            )
        drafts.append(draft)
    return drafts


class AdminScheduleService:
    """Changes slots while retaining an audit trail and confirmed reservations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_slots(
        self, admin: Admin, drafts: list[SlotDraft]
    ) -> list[AvailableSlot]:
        created: list[AvailableSlot] = []
        for draft in drafts:
            conflict = await self.session.scalar(
                select(AvailableSlot.id)
                .where(
                    AvailableSlot.starts_at < draft.ends_at,
                    AvailableSlot.ends_at > draft.starts_at,
                )
                .limit(1)
            )
            if conflict is not None:
                raise AdminScheduleError("Этот промежуток пересекается с существующим слотом.")
            slot = AvailableSlot(
                id=uuid4(),
                starts_at=draft.starts_at,
                ends_at=draft.ends_at,
                is_available=True,
            )
            self.session.add(slot)
            self.session.add(
                AdminAuditLog(
                    admin_id=admin.id,
                    action="slot_created",
                    entity_type="available_slot",
                    entity_id=slot.id,
                    old_value=None,
                    new_value={
                        "starts_at": slot.starts_at.isoformat(),
                        "ends_at": slot.ends_at.isoformat(),
                    },
                )
            )
            created.append(slot)
        await self.session.flush()
        return created

    async def list_open_slots(
        self, *, now: datetime | None = None, limit: int = 20
    ) -> list[AvailableSlot]:
        current = now or datetime.now(UTC)
        result = await self.session.execute(
            select(AvailableSlot)
            .where(
                AvailableSlot.is_available.is_(True),
                AvailableSlot.blocked_reason.is_(None),
                AvailableSlot.starts_at > current,
            )
            .order_by(AvailableSlot.starts_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def close_slot(self, admin: Admin, slot_id: UUID) -> AvailableSlot:
        slot = await self.session.get(AvailableSlot, slot_id, with_for_update=True)
        if slot is None:
            raise AdminScheduleError("Слот не найден.")
        if slot.starts_at <= datetime.now(UTC):
            raise AdminScheduleError("Прошедший слот нельзя изменить.")
        reservation = await self.session.scalar(
            select(AppointmentSlotReservation.id)
            .where(
                AppointmentSlotReservation.slot_id == slot.id,
                AppointmentSlotReservation.status.in_(
                    (ReservationStatus.ACTIVE, ReservationStatus.CONFIRMED)
                ),
            )
            .limit(1)
        )
        if reservation is not None:
            raise AdminScheduleError(
                "Слот уже зарезервирован или подтверждён — отмените либо перенесите запись."
            )
        previous = {
            "is_available": slot.is_available,
            "blocked_reason": slot.blocked_reason,
        }
        slot.is_available = False
        slot.blocked_reason = "Закрыт администратором"
        self.session.add(
            AdminAuditLog(
                admin_id=admin.id,
                action="slot_closed",
                entity_type="available_slot",
                entity_id=slot.id,
                old_value=previous,
                new_value={
                    "is_available": slot.is_available,
                    "blocked_reason": slot.blocked_reason,
                },
            )
        )
        await self.session.flush()
        return slot
