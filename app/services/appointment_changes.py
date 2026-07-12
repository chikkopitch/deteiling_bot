"""Safe user/admin appointment rescheduling and cancellation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import AppointmentStatus, ReminderStatus, ReservationStatus
from app.database.models import (
    Admin,
    AdminAuditLog,
    AppointmentHistory,
    AppointmentSlotReservation,
    Reminder,
    User,
)
from app.database.repositories import (
    AdminAuditLogRepository,
    AppointmentHistoryRepository,
    AppointmentRepository,
    AvailableSlotRepository,
    ReminderRepository,
    ReservationRepository,
)
from app.services.schedule import SlotUnavailableError
from app.services.vehicle_selection import VehicleSelectionError, clean_user_text


class AppointmentChangeService:
    def __init__(
        self, session: AsyncSession, *, deadline_hours: int, reservation_minutes: int
    ) -> None:
        self.session = session
        self.deadline = timedelta(hours=deadline_hours)
        self.reservation_minutes = reservation_minutes
        self.appointments = AppointmentRepository(session)
        self.slots = AvailableSlotRepository(session)
        self.reservations = ReservationRepository(session)
        self.reminders = ReminderRepository(session)
        self.history = AppointmentHistoryRepository(session)
        self.audit = AdminAuditLogRepository(session)

    def _check_change_allowed(
        self, appointment, now: datetime, *, bypass_deadline: bool
    ) -> None:
        if appointment.status != AppointmentStatus.CONFIRMED:
            raise VehicleSelectionError("Изменять можно только подтверждённую запись.")
        if appointment.scheduled_at is None or appointment.slot_id is None:
            raise VehicleSelectionError("У записи отсутствует закреплённое время.")
        if not bypass_deadline and appointment.scheduled_at - now < self.deadline:
            raise VehicleSelectionError(
                "Срок самостоятельного изменения истёк. Свяжитесь с менеджером."
            )

    async def reserve_new_slot(
        self,
        actor: User | Admin,
        appointment_id: UUID,
        slot_id: UUID,
        *,
        now: datetime | None = None,
        as_admin: bool = False,
    ) -> AppointmentSlotReservation:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        appointment = await self.appointments.get_for_update(appointment_id)
        if appointment is None or (not as_admin and appointment.user_id != actor.id):
            raise VehicleSelectionError("Запись не найдена.")
        self._check_change_allowed(appointment, current, bypass_deadline=as_admin)
        existing = await self.reservations.get_for_appointment_by_status_for_update(
            appointment.id, ReservationStatus.ACTIVE
        )
        if existing is not None:
            existing.status = ReservationStatus.CANCELLED
            existing_slot = await self.slots.get_for_update(existing.slot_id)
            if existing_slot and existing_slot.blocked_reason is None:
                existing_slot.is_available = True
        slot = await self.slots.get_for_update(slot_id)
        if (
            slot is None
            or slot.starts_at <= current
            or slot.blocked_reason
            or not slot.is_available
        ):
            raise SlotUnavailableError("Выбранное время уже недоступно.")
        blocking = await self.reservations.get_blocking_for_slot_for_update(slot.id)
        if blocking is not None:
            raise SlotUnavailableError("Выбранное время уже занято.")
        reservation = AppointmentSlotReservation(
            appointment_id=appointment.id,
            slot_id=slot.id,
            reserved_until=current + timedelta(minutes=self.reservation_minutes),
            status=ReservationStatus.ACTIVE,
        )
        try:
            async with self.session.begin_nested():
                await self.reservations.add(reservation)
        except IntegrityError as error:
            raise SlotUnavailableError("Выбранное время уже занято.") from error
        slot.is_available = False
        await self.session.flush()
        return reservation

    async def confirm_reschedule(
        self,
        actor: User | Admin,
        appointment_id: UUID,
        *,
        reminder_hours: tuple[int, ...],
        now: datetime | None = None,
        as_admin: bool = False,
    ) -> None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        appointment = await self.appointments.get_for_update(appointment_id)
        if appointment is None or (not as_admin and appointment.user_id != actor.id):
            raise VehicleSelectionError("Запись не найдена.")
        self._check_change_allowed(appointment, current, bypass_deadline=as_admin)
        old_reservation = (
            await self.reservations.get_for_appointment_by_status_for_update(
                appointment.id, ReservationStatus.CONFIRMED
            )
        )
        new_reservation = (
            await self.reservations.get_for_appointment_by_status_for_update(
                appointment.id, ReservationStatus.ACTIVE
            )
        )
        if old_reservation is None or new_reservation is None:
            raise SlotUnavailableError("Резерв для переноса не найден.")
        new_slot = await self.slots.get_for_update(new_reservation.slot_id)
        if (
            new_slot is None
            or new_slot.blocked_reason is not None
            or new_reservation.reserved_until is None
            or new_reservation.reserved_until <= current
        ):
            raise SlotUnavailableError(
                "Новый слот потерял доступность. Старая запись сохранена."
            )
        blocking = await self.reservations.get_blocking_for_slot_for_update(new_slot.id)
        if blocking is None or blocking.id != new_reservation.id:
            raise SlotUnavailableError(
                "Новый слот потерял доступность. Старая запись сохранена."
            )
        old_slot = await self.slots.get_for_update(old_reservation.slot_id)
        old_time = appointment.scheduled_at
        old_reservation.status = ReservationStatus.CANCELLED
        new_reservation.status = ReservationStatus.CONFIRMED
        new_reservation.reserved_until = None
        if old_slot and old_slot.blocked_reason is None:
            old_slot.is_available = True
        new_slot.is_available = False
        appointment.slot_id = new_slot.id
        appointment.scheduled_at = new_slot.starts_at
        await self.reminders.cancel_open(appointment.id)
        for hours in reminder_hours:
            scheduled = new_slot.starts_at - timedelta(hours=hours)
            await self.reminders.add(
                Reminder(
                    appointment_id=appointment.id,
                    reminder_type=f"rescheduled_before_{hours}h",
                    scheduled_for=max(scheduled, current),
                    status=ReminderStatus.PENDING,
                )
            )
        await self.history.add(
            AppointmentHistory(
                appointment_id=appointment.id,
                action="rescheduled",
                old_value={
                    "scheduled_at": old_time.isoformat(),
                    "slot_id": str(old_reservation.slot_id),
                },
                new_value={
                    "scheduled_at": new_slot.starts_at.isoformat(),
                    "slot_id": str(new_slot.id),
                },
                changed_by_admin_id=actor.id if as_admin else None,
                changed_by_user_id=None if as_admin else actor.id,
            )
        )
        if as_admin:
            await self.audit.add(
                AdminAuditLog(
                    admin_id=actor.id,
                    action="appointment_rescheduled",
                    entity_type="appointment",
                    entity_id=appointment.id,
                    old_value={
                        "scheduled_at": old_time.isoformat(),
                        "slot_id": str(old_reservation.slot_id),
                    },
                    new_value={
                        "scheduled_at": new_slot.starts_at.isoformat(),
                        "slot_id": str(new_slot.id),
                    },
                )
            )
        await self.session.flush()

    async def cancel(
        self,
        actor: User | Admin,
        appointment_id: UUID,
        reason: str,
        *,
        now: datetime | None = None,
        as_admin: bool = False,
    ) -> AppointmentStatus:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        normalized = clean_user_text(reason, min_length=2, max_length=500)
        appointment = await self.appointments.get_for_update(appointment_id)
        if appointment is None or (not as_admin and appointment.user_id != actor.id):
            raise VehicleSelectionError("Запись не найдена.")
        self._check_change_allowed(appointment, current, bypass_deadline=as_admin)
        reservation = await self.reservations.get_for_appointment_by_status_for_update(
            appointment.id, ReservationStatus.CONFIRMED
        )
        slot = await self.slots.get_for_update(appointment.slot_id)
        if reservation:
            reservation.status = ReservationStatus.CANCELLED
        active = await self.reservations.get_for_appointment_by_status_for_update(
            appointment.id, ReservationStatus.ACTIVE
        )
        if active:
            active.status = ReservationStatus.CANCELLED
            active_slot = await self.slots.get_for_update(active.slot_id)
            if active_slot and active_slot.blocked_reason is None:
                active_slot.is_available = True
        if slot and slot.blocked_reason is None:
            slot.is_available = slot.starts_at > current
        new_status = (
            AppointmentStatus.CANCELLED_BY_ADMIN
            if as_admin
            else AppointmentStatus.CANCELLED_BY_USER
        )
        appointment.status = new_status
        appointment.cancellation_reason = normalized
        appointment.cancelled_at = current
        await self.reminders.cancel_open(appointment.id)
        await self.history.add(
            AppointmentHistory(
                appointment_id=appointment.id,
                action=new_status.value,
                old_value={"status": AppointmentStatus.CONFIRMED.value},
                new_value={"status": new_status.value, "reason": normalized},
                changed_by_admin_id=actor.id if as_admin else None,
                changed_by_user_id=None if as_admin else actor.id,
            )
        )
        if as_admin:
            await self.audit.add(
                AdminAuditLog(
                    admin_id=actor.id,
                    action="appointment_cancelled",
                    entity_type="appointment",
                    entity_id=appointment.id,
                    old_value={"status": AppointmentStatus.CONFIRMED.value},
                    new_value={"status": new_status.value, "reason": normalized},
                )
            )
        await self.session.flush()
        return new_status
