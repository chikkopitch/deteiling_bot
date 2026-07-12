"""Administrative confirmation and rejection use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import AppointmentStatus, ReminderStatus, ReservationStatus
from app.database.models import (
    Admin,
    AdminAuditLog,
    Appointment,
    AppointmentHistory,
    AvailableSlot,
    Reminder,
)
from app.database.repositories import (
    AdminAuditLogRepository,
    AppointmentHistoryRepository,
    AppointmentRepository,
    ReminderRepository,
    ReservationRepository,
)
from app.services.vehicle_selection import VehicleSelectionError, clean_user_text


@dataclass(slots=True, frozen=True)
class AdminAppointmentResult:
    appointment: Appointment
    reminders_created: int = 0
    reminders_cancelled: int = 0


class AdminAppointmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.appointments = AppointmentRepository(session)
        self.reservations = ReservationRepository(session)
        self.reminders = ReminderRepository(session)
        self.history = AppointmentHistoryRepository(session)
        self.audit = AdminAuditLogRepository(session)

    async def confirm(
        self,
        admin: Admin,
        appointment_id: UUID,
        reminder_hours: tuple[int, ...],
        *,
        now: datetime | None = None,
    ) -> AdminAppointmentResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        appointment = await self.appointments.get_for_update(appointment_id)
        if appointment is None:
            raise VehicleSelectionError("Заявка не найдена.")
        if appointment.status != AppointmentStatus.WAITING_ADMIN:
            raise VehicleSelectionError("Заявка уже обработана.")
        if appointment.slot_id is None or appointment.scheduled_at is None:
            raise VehicleSelectionError("За заявкой не закреплён слот.")
        reservation = await self.reservations.get_blocking_for_appointment_for_update(
            appointment.id
        )
        if (
            reservation is None
            or reservation.status != ReservationStatus.CONFIRMED
            or reservation.slot_id != appointment.slot_id
        ):
            raise VehicleSelectionError("Подтверждённый резерв не найден.")
        slot = await self.session.get(
            AvailableSlot, appointment.slot_id, with_for_update=True
        )
        if slot is None or slot.blocked_reason is not None:
            raise VehicleSelectionError("Слот недоступен.")
        if slot.starts_at != appointment.scheduled_at:
            raise VehicleSelectionError("Время слота не совпадает с заявкой.")

        appointment.status = AppointmentStatus.CONFIRMED
        appointment.confirmed_by_admin_id = admin.id
        appointment.confirmed_at = current
        slot.is_available = False
        await self.history.add(
            AppointmentHistory(
                appointment_id=appointment.id,
                action="confirmed",
                old_value={"status": AppointmentStatus.WAITING_ADMIN.value},
                new_value={"status": AppointmentStatus.CONFIRMED.value},
                changed_by_admin_id=admin.id,
            )
        )
        await self.audit.add(
            AdminAuditLog(
                admin_id=admin.id,
                action="appointment_confirmed",
                entity_type="appointment",
                entity_id=appointment.id,
                old_value={"status": AppointmentStatus.WAITING_ADMIN.value},
                new_value={"status": AppointmentStatus.CONFIRMED.value},
            )
        )

        created = 0
        for hours in reminder_hours:
            reminder_type = f"before_{hours}h"
            if await self.reminders.exists_for_type(appointment.id, reminder_type):
                continue
            scheduled_for = appointment.scheduled_at - timedelta(hours=hours)
            if scheduled_for < current:
                scheduled_for = current
            await self.reminders.add(
                Reminder(
                    appointment_id=appointment.id,
                    reminder_type=reminder_type,
                    scheduled_for=scheduled_for,
                    status=ReminderStatus.PENDING,
                )
            )
            created += 1
        await self.session.flush()
        return AdminAppointmentResult(appointment, reminders_created=created)

    async def reject(
        self,
        admin: Admin,
        appointment_id: UUID,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> AdminAppointmentResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        normalized_reason = clean_user_text(reason, min_length=2, max_length=500)
        appointment = await self.appointments.get_for_update(appointment_id)
        if appointment is None:
            raise VehicleSelectionError("Заявка не найдена.")
        if appointment.status != AppointmentStatus.WAITING_ADMIN:
            raise VehicleSelectionError("Заявка уже обработана.")
        reservation = await self.reservations.get_blocking_for_appointment_for_update(
            appointment.id
        )
        slot = None
        if reservation is not None:
            slot = await self.session.get(
                AvailableSlot, reservation.slot_id, with_for_update=True
            )
            reservation.status = ReservationStatus.CANCELLED
        if slot is not None and slot.blocked_reason is None:
            slot.is_available = slot.starts_at > current

        appointment.status = AppointmentStatus.REJECTED
        appointment.rejection_reason = normalized_reason
        cancelled = await self.reminders.cancel_future(appointment.id, current)
        await self.history.add(
            AppointmentHistory(
                appointment_id=appointment.id,
                action="rejected",
                old_value={"status": AppointmentStatus.WAITING_ADMIN.value},
                new_value={
                    "status": AppointmentStatus.REJECTED.value,
                    "reason": normalized_reason,
                },
                changed_by_admin_id=admin.id,
            )
        )
        await self.audit.add(
            AdminAuditLog(
                admin_id=admin.id,
                action="appointment_rejected",
                entity_type="appointment",
                entity_id=appointment.id,
                old_value={"status": AppointmentStatus.WAITING_ADMIN.value},
                new_value={
                    "status": AppointmentStatus.REJECTED.value,
                    "reason": normalized_reason,
                },
            )
        )
        await self.session.flush()
        return AdminAppointmentResult(appointment, reminders_cancelled=cancelled)
