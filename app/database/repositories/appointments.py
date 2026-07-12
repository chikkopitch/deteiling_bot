"""Appointment and reservation repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, or_, select

from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import Appointment, AppointmentSlotReservation, AvailableSlot
from app.database.repositories.base import BaseRepository


class AppointmentRepository(BaseRepository[Appointment]):
    model = Appointment

    async def get_for_update(self, appointment_id: UUID) -> Appointment | None:
        result = await self.session.execute(
            select(Appointment)
            .where(Appointment.id == appointment_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_draft_for_user(self, user_id: UUID) -> Appointment | None:
        result = await self.session.execute(
            select(Appointment)
            .where(
                Appointment.user_id == user_id,
                Appointment.status == AppointmentStatus.DRAFT,
            )
            .order_by(Appointment.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_owned_draft_for_update(
        self, appointment_id: UUID, user_id: UUID
    ) -> Appointment | None:
        result = await self.session.execute(
            select(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.user_id == user_id,
                Appointment.status == AppointmentStatus.DRAFT,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        statuses: tuple[AppointmentStatus, ...] | None = None,
    ) -> list[Appointment]:
        statement = select(Appointment).where(Appointment.user_id == user_id)
        if statuses:
            statement = statement.where(Appointment.status.in_(statuses))
        result = await self.session.execute(
            statement.order_by(
                Appointment.scheduled_at.asc().nulls_last(),
                Appointment.created_at.desc(),
            )
        )
        return list(result.scalars())


class AvailableSlotRepository(BaseRepository[AvailableSlot]):
    model = AvailableSlot

    async def list_available_between(
        self, starts_at: datetime, ends_at: datetime, now: datetime
    ) -> list[AvailableSlot]:
        blocking_reservation = exists(
            select(AppointmentSlotReservation.id).where(
                AppointmentSlotReservation.slot_id == AvailableSlot.id,
                or_(
                    AppointmentSlotReservation.status == ReservationStatus.CONFIRMED,
                    and_(
                        AppointmentSlotReservation.status == ReservationStatus.ACTIVE,
                        AppointmentSlotReservation.reserved_until > now,
                    ),
                ),
            )
        )
        result = await self.session.execute(
            select(AvailableSlot)
            .where(
                AvailableSlot.is_available.is_(True),
                AvailableSlot.blocked_reason.is_(None),
                AvailableSlot.starts_at >= starts_at,
                AvailableSlot.starts_at < ends_at,
                AvailableSlot.starts_at > now,
                ~blocking_reservation,
            )
            .order_by(AvailableSlot.starts_at)
        )
        return list(result.scalars())

    async def get_for_update(self, slot_id: UUID) -> AvailableSlot | None:
        result = await self.session.execute(
            select(AvailableSlot).where(AvailableSlot.id == slot_id).with_for_update()
        )
        return result.scalar_one_or_none()


class ReservationRepository(BaseRepository[AppointmentSlotReservation]):
    model = AppointmentSlotReservation

    async def get_blocking_for_slot(
        self, slot_id: UUID
    ) -> AppointmentSlotReservation | None:
        result = await self.session.execute(
            select(AppointmentSlotReservation).where(
                AppointmentSlotReservation.slot_id == slot_id,
                AppointmentSlotReservation.status.in_(
                    (ReservationStatus.ACTIVE, ReservationStatus.CONFIRMED)
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_blocking_for_slot_for_update(
        self, slot_id: UUID
    ) -> AppointmentSlotReservation | None:
        result = await self.session.execute(
            select(AppointmentSlotReservation)
            .where(
                AppointmentSlotReservation.slot_id == slot_id,
                AppointmentSlotReservation.status.in_(
                    (ReservationStatus.ACTIVE, ReservationStatus.CONFIRMED)
                ),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_blocking_for_appointment_for_update(
        self, appointment_id: UUID
    ) -> AppointmentSlotReservation | None:
        result = await self.session.execute(
            select(AppointmentSlotReservation)
            .where(
                AppointmentSlotReservation.appointment_id == appointment_id,
                AppointmentSlotReservation.status.in_(
                    (ReservationStatus.ACTIVE, ReservationStatus.CONFIRMED)
                ),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_for_appointment_by_status_for_update(
        self, appointment_id: UUID, status: ReservationStatus
    ) -> AppointmentSlotReservation | None:
        result = await self.session.execute(
            select(AppointmentSlotReservation)
            .where(
                AppointmentSlotReservation.appointment_id == appointment_id,
                AppointmentSlotReservation.status == status,
            )
            .order_by(AppointmentSlotReservation.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()
