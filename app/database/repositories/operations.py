"""Manager queue, reminder queue, history, and audit repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update

from app.database.enums import ManagerRequestStatus, ReminderStatus
from app.database.models import (
    AdminAuditLog,
    AppointmentHistory,
    ManagerRequest,
    Reminder,
)
from app.database.repositories.base import BaseRepository


class ManagerRequestRepository(BaseRepository[ManagerRequest]):
    model = ManagerRequest

    async def list_queue(
        self,
        statuses: tuple[ManagerRequestStatus, ...] = (
            ManagerRequestStatus.OPEN,
            ManagerRequestStatus.WAITING_MANAGER,
        ),
    ) -> list[ManagerRequest]:
        result = await self.session.execute(
            select(ManagerRequest)
            .where(ManagerRequest.status.in_(statuses))
            .order_by(ManagerRequest.created_at)
        )
        return list(result.scalars())


class ReminderRepository(BaseRepository[Reminder]):
    model = Reminder

    async def acquire_due(self, now: datetime, limit: int = 100) -> list[Reminder]:
        result = await self.session.execute(
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.PENDING,
                Reminder.scheduled_for <= now,
            )
            .order_by(Reminder.scheduled_for, Reminder.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars())

    async def exists_for_type(self, appointment_id: UUID, reminder_type: str) -> bool:
        value = await self.session.scalar(
            select(Reminder.id).where(
                Reminder.appointment_id == appointment_id,
                Reminder.reminder_type == reminder_type,
            )
        )
        return value is not None

    async def cancel_future(self, appointment_id: UUID, now: datetime) -> int:
        result = await self.session.execute(
            update(Reminder)
            .where(
                Reminder.appointment_id == appointment_id,
                Reminder.scheduled_for > now,
                Reminder.status.in_(
                    (ReminderStatus.PENDING, ReminderStatus.PROCESSING)
                ),
            )
            .values(
                status=ReminderStatus.CANCELLED,
                processing_started_at=None,
            )
        )
        return int(result.rowcount or 0)

    async def cancel_open(self, appointment_id: UUID) -> int:
        result = await self.session.execute(
            update(Reminder)
            .where(
                Reminder.appointment_id == appointment_id,
                Reminder.status.in_(
                    (ReminderStatus.PENDING, ReminderStatus.PROCESSING)
                ),
            )
            .values(status=ReminderStatus.CANCELLED, processing_started_at=None)
        )
        return int(result.rowcount or 0)


class AppointmentHistoryRepository(BaseRepository[AppointmentHistory]):
    model = AppointmentHistory

    async def list_for_appointment(
        self, appointment_id: UUID
    ) -> list[AppointmentHistory]:
        result = await self.session.execute(
            select(AppointmentHistory)
            .where(AppointmentHistory.appointment_id == appointment_id)
            .order_by(AppointmentHistory.created_at)
        )
        return list(result.scalars())


class AdminAuditLogRepository(BaseRepository[AdminAuditLog]):
    model = AdminAuditLog

    async def list_for_entity(
        self, entity_type: str, entity_id: UUID
    ) -> list[AdminAuditLog]:
        result = await self.session.execute(
            select(AdminAuditLog)
            .where(
                AdminAuditLog.entity_type == entity_type,
                AdminAuditLog.entity_id == entity_id,
            )
            .order_by(AdminAuditLog.created_at)
        )
        return list(result.scalars())
