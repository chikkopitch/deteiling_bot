"""Appointment photo metadata repository."""

from uuid import UUID

from sqlalchemy import func, select

from app.database.models import AppointmentPhoto
from app.database.repositories.base import BaseRepository


class AppointmentPhotoRepository(BaseRepository[AppointmentPhoto]):
    model = AppointmentPhoto

    async def count_for_appointment(self, appointment_id: UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(AppointmentPhoto)
            .where(AppointmentPhoto.appointment_id == appointment_id)
        )
        return int(count or 0)

    async def exists(self, appointment_id: UUID, telegram_file_unique_id: str) -> bool:
        value = await self.session.scalar(
            select(AppointmentPhoto.id).where(
                AppointmentPhoto.appointment_id == appointment_id,
                AppointmentPhoto.telegram_file_unique_id == telegram_file_unique_id,
            )
        )
        return value is not None

    async def get_last(self, appointment_id: UUID) -> AppointmentPhoto | None:
        result = await self.session.execute(
            select(AppointmentPhoto)
            .where(AppointmentPhoto.appointment_id == appointment_id)
            .order_by(AppointmentPhoto.created_at.desc(), AppointmentPhoto.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_appointment(
        self, appointment_id: UUID
    ) -> list[AppointmentPhoto]:
        result = await self.session.execute(
            select(AppointmentPhoto)
            .where(AppointmentPhoto.appointment_id == appointment_id)
            .order_by(AppointmentPhoto.created_at, AppointmentPhoto.id)
        )
        return list(result.scalars())
