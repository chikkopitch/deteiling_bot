from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Booking,
    BookingPhoto,
    BookingStatus,
    Notification,
    NotificationStatus,
    NotificationType,
    Service,
    SlotStatus,
    TimeSlot,
    User,
    Vehicle,
)
from app.repositories import BookingRepository, NotificationRepository, SlotRepository
from app.schemas import BookingDraft
from app.services.errors import InvalidTransitionError, SlotUnavailableError
from app.utils.datetime import utc_now
from app.utils.phone import normalize_phone

TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.DRAFT: {BookingStatus.PENDING, BookingStatus.CANCELLED_BY_CLIENT},
    BookingStatus.PENDING: {
        BookingStatus.CONFIRMED,
        BookingStatus.RESCHEDULE_REQUESTED,
        BookingStatus.CANCELLED_BY_CLIENT,
        BookingStatus.CANCELLED_BY_ADMIN,
    },
    BookingStatus.CONFIRMED: {
        BookingStatus.RESCHEDULE_REQUESTED,
        BookingStatus.CANCELLED_BY_CLIENT,
        BookingStatus.CANCELLED_BY_ADMIN,
        BookingStatus.COMPLETED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.RESCHEDULE_REQUESTED: {
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELLED_BY_CLIENT,
        BookingStatus.CANCELLED_BY_ADMIN,
    },
    BookingStatus.CANCELLED_BY_CLIENT: set(),
    BookingStatus.CANCELLED_BY_ADMIN: set(),
    BookingStatus.COMPLETED: set(),
    BookingStatus.NO_SHOW: set(),
}


def ensure_transition(current: BookingStatus, target: BookingStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise InvalidTransitionError(f"Transition {current} -> {target} is forbidden")


def is_expired(value: datetime | None, now: datetime | None = None) -> bool:
    if value is None:
        return True
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return normalized <= (now or utc_now())


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.slots = SlotRepository(session)

    async def hold_slot(self, slot_id: UUID, user: User, minutes: int) -> TimeSlot:
        slot = await self.slots.lock(slot_id)
        now = utc_now()
        if (
            slot is None
            or slot.starts_at <= now
            or (
                slot.status == SlotStatus.HELD
                and slot.hold_expires_at
                and not is_expired(slot.hold_expires_at, now)
                and slot.held_by_user_id != user.id
            )
            or slot.status in (SlotStatus.BOOKED, SlotStatus.BLOCKED)
        ):
            raise SlotUnavailableError("Это время уже недоступно")
        slot.status, slot.held_by_user_id, slot.hold_expires_at = (
            SlotStatus.HELD,
            user.id,
            now + timedelta(minutes=minutes),
        )
        await self.session.flush()
        return slot

    async def submit(self, user: User, data: BookingDraft) -> Booking:
        existing = await self.bookings.by_idempotency_key(data.idempotency_key)
        if existing:
            return existing
        slot = await self.slots.lock(data.slot_id)
        now = utc_now()
        if (
            slot is None
            or slot.status != SlotStatus.HELD
            or slot.held_by_user_id != user.id
            or is_expired(slot.hold_expires_at, now)
        ):
            raise SlotUnavailableError("Временная бронь истекла")
        vehicle = Vehicle(
            user_id=user.id,
            brand_name=data.brand.strip().title(),
            model_name=data.model.strip(),
            year=data.year,
            vehicle_class=data.vehicle_class,
        )
        self.session.add(vehicle)
        await self.session.flush()
        services = list(
            await self.session.scalars(
                select(Service).where(
                    Service.id.in_(data.service_ids),
                    Service.is_active,
                    Service.deleted_at.is_(None),
                )
            )
        )
        if len(services) != len(set(data.service_ids)):
            raise ValueError("Одна или несколько выбранных услуг больше недоступны")
        booking = Booking(
            user_id=user.id,
            vehicle_id=vehicle.id,
            slot_id=slot.id,
            status=BookingStatus.PENDING,
            customer_name=" ".join(data.customer_name.split()),
            customer_phone=normalize_phone(data.customer_phone),
            comment=data.comment,
            estimated_min=data.estimated_min,
            estimated_max=data.estimated_max,
            idempotency_key=data.idempotency_key,
        )
        try:
            self.session.add(booking)
            booking.services = services
            await self.session.flush()
            self.session.add_all(
                [
                    BookingPhoto(
                        booking_id=booking.id,
                        file_id=photo.file_id,
                        unique_file_id=photo.unique_file_id,
                        mime_type=photo.mime_type,
                        size_bytes=photo.size_bytes,
                        sort_order=order,
                    )
                    for order, photo in enumerate(data.photos)
                ]
            )
            user.phone = normalize_phone(data.customer_phone)
            slot.status, slot.held_by_user_id, slot.hold_expires_at = SlotStatus.BOOKED, None, None
            self.session.add(
                AuditLog(
                    actor_user_id=user.id,
                    action="booking.submitted",
                    entity_type="booking",
                    entity_id=booking.id,
                    details={},
                )
            )
            await self.session.commit()
            await self.session.refresh(booking)
            return booking
        except IntegrityError as error:
            await self.session.rollback()
            existing = await self.bookings.by_idempotency_key(data.idempotency_key)
            if existing:
                return existing
            raise SlotUnavailableError("Это время уже занято") from error

    async def change_status(
        self,
        booking_id: UUID,
        target: BookingStatus,
        actor_id: UUID | None = None,
        reason: str | None = None,
    ) -> Booking:
        booking = await self.bookings.lock(booking_id)
        if booking is None:
            raise LookupError("Booking not found")
        if booking.status == target:
            return booking
        ensure_transition(booking.status, target)
        booking.status = target
        booking.cancellation_reason = reason
        if target in (BookingStatus.CANCELLED_BY_CLIENT, BookingStatus.CANCELLED_BY_ADMIN):
            if booking.slot_id:
                slot = await self.slots.lock(booking.slot_id)
                if slot and slot.status == SlotStatus.BOOKED:
                    slot.status = SlotStatus.AVAILABLE
            for note in await self._pending_notifications(booking.id):
                note.status = NotificationStatus.CANCELLED
        self.session.add(
            AuditLog(
                actor_user_id=actor_id,
                action=f"booking.{target.value}",
                entity_type="booking",
                entity_id=booking.id,
                details={"reason": reason or ""},
            )
        )
        await self.session.commit()
        return booking

    async def propose_reschedule(self, booking_id: UUID, slot_id: UUID, actor_id: UUID) -> Booking:
        booking = await self.bookings.lock(booking_id)
        slot = await self.slots.lock(slot_id)
        if booking is None or slot is None:
            raise LookupError("Запись или слот не найдены")
        if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
            raise InvalidTransitionError("Для этой записи нельзя предложить перенос")
        if slot.status != SlotStatus.AVAILABLE or slot.starts_at <= utc_now():
            raise SlotUnavailableError("Это время уже недоступно")
        slot.status = SlotStatus.HELD
        slot.held_by_user_id = booking.user_id
        slot.hold_expires_at = utc_now() + timedelta(minutes=30)
        booking.proposed_slot_id = slot.id
        booking.status = BookingStatus.RESCHEDULE_REQUESTED
        self.session.add(
            AuditLog(
                actor_user_id=actor_id,
                action="booking.reschedule_proposed",
                entity_type="booking",
                entity_id=booking.id,
                details={"slot_id": str(slot.id)},
            )
        )
        await self.session.commit()
        return booking

    async def accept_reschedule(self, booking_id: UUID, user_id: UUID) -> Booking:
        booking = await self.bookings.lock(booking_id)
        if booking is None or booking.user_id != user_id or booking.proposed_slot_id is None:
            raise LookupError("Предложение переноса не найдено")
        if booking.status != BookingStatus.RESCHEDULE_REQUESTED:
            raise InvalidTransitionError("Предложение уже неактуально")
        new_slot = await self.slots.lock(booking.proposed_slot_id)
        old_slot = await self.slots.lock(booking.slot_id) if booking.slot_id else None
        if (
            new_slot is None
            or new_slot.status != SlotStatus.HELD
            or new_slot.held_by_user_id != user_id
            or is_expired(new_slot.hold_expires_at)
        ):
            raise SlotUnavailableError("Предложенное время уже недоступно")
        if old_slot and old_slot.status == SlotStatus.BOOKED:
            old_slot.status = SlotStatus.AVAILABLE
        new_slot.status, new_slot.held_by_user_id, new_slot.hold_expires_at = (
            SlotStatus.BOOKED,
            None,
            None,
        )
        booking.slot_id, booking.proposed_slot_id, booking.status = (
            new_slot.id,
            None,
            BookingStatus.PENDING,
        )
        self.session.add(
            AuditLog(
                actor_user_id=user_id,
                action="booking.reschedule_accepted",
                entity_type="booking",
                entity_id=booking.id,
                details={"slot_id": str(new_slot.id)},
            )
        )
        await self.session.commit()
        return booking

    async def refresh_reminders(self, booking_id: UUID, reminders: tuple[int, ...]) -> None:
        booking = await self.bookings.lock(booking_id)
        if booking is None or booking.slot_id is None:
            raise LookupError("Запись не найдена")
        slot = await self.slots.lock(booking.slot_id)
        if slot is None:
            raise LookupError("Слот не найден")
        await NotificationRepository(self.session).cancel_pending_for_booking(booking.id)
        await self._create_reminders(booking, slot, reminders)
        await self.session.commit()

    async def decline_reschedule(self, booking_id: UUID, user_id: UUID) -> Booking:
        booking = await self.bookings.lock(booking_id)
        if booking is None or booking.user_id != user_id or booking.proposed_slot_id is None:
            raise LookupError("Предложение переноса не найдено")
        proposed = await self.slots.lock(booking.proposed_slot_id)
        if proposed and proposed.status == SlotStatus.HELD and proposed.held_by_user_id == user_id:
            proposed.status, proposed.held_by_user_id, proposed.hold_expires_at = (
                SlotStatus.AVAILABLE,
                None,
                None,
            )
        booking.proposed_slot_id, booking.status = None, BookingStatus.PENDING
        self.session.add(
            AuditLog(
                actor_user_id=user_id,
                action="booking.reschedule_declined",
                entity_type="booking",
                entity_id=booking.id,
                details={},
            )
        )
        await self.session.commit()
        return booking

    async def reschedule_by_client(
        self,
        booking_id: UUID,
        user_id: UUID,
        new_slot_id: UUID,
        reminders: tuple[int, ...],
        minimum_hours: int,
    ) -> Booking:
        booking = await self.bookings.lock(booking_id)
        if booking is None or booking.user_id != user_id:
            raise LookupError("Запись не найдена")
        if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
            raise InvalidTransitionError("Эту запись нельзя перенести")
        new_slot = await self.slots.lock(new_slot_id)
        old_slot = await self.slots.lock(booking.slot_id) if booking.slot_id else None
        cutoff = utc_now() + timedelta(hours=minimum_hours)
        if (
            new_slot is None
            or new_slot.status != SlotStatus.AVAILABLE
            or new_slot.starts_at <= cutoff
        ):
            raise SlotUnavailableError("Выбранное время недоступно или слишком близко")
        previous_status = booking.status
        if old_slot and old_slot.status == SlotStatus.BOOKED:
            old_slot.status = SlotStatus.AVAILABLE
        new_slot.status = SlotStatus.BOOKED
        booking.slot_id = new_slot.id
        await NotificationRepository(self.session).cancel_pending_for_booking(booking.id)
        if previous_status == BookingStatus.CONFIRMED:
            await self._create_reminders(booking, new_slot, reminders)
        self.session.add(
            AuditLog(
                actor_user_id=user_id,
                action="booking.rescheduled_by_client",
                entity_type="booking",
                entity_id=booking.id,
                details={
                    "old_slot_id": str(old_slot.id) if old_slot else None,
                    "new_slot_id": str(new_slot.id),
                },
            )
        )
        await self.session.commit()
        return booking

    async def confirm(
        self, booking_id: UUID, actor_id: UUID, reminders: tuple[int, ...]
    ) -> Booking:
        booking = await self.change_status(booking_id, BookingStatus.CONFIRMED, actor_id)
        if not booking.slot:
            await self.session.refresh(booking, ["slot"])
        if booking.slot:
            await self._create_reminders(booking, booking.slot, reminders)
            await self.session.commit()
        return booking

    async def _create_reminders(
        self, booking: Booking, slot: TimeSlot, reminders: tuple[int, ...]
    ) -> None:
        repository = NotificationRepository(self.session)
        for hours in reminders:
            scheduled = slot.starts_at - timedelta(hours=hours)
            key = f"booking:{booking.id}:slot:{slot.id}:reminder:{hours}"
            if scheduled > utc_now() and await repository.by_idempotency_key(key) is None:
                self.session.add(
                    Notification(
                        booking_id=booking.id,
                        user_id=booking.user_id,
                        type=NotificationType.REMINDER,
                        scheduled_at=scheduled,
                        idempotency_key=key,
                    )
                )

    async def _pending_notifications(self, booking_id: UUID) -> list[Notification]:
        return list(
            await self.session.scalars(
                select(Notification).where(
                    Notification.booking_id == booking_id,
                    Notification.status.in_((NotificationStatus.PENDING, NotificationStatus.RETRY)),
                )
            )
        )
