"""Store Telegram photo metadata without downloading files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import MediaType
from app.database.models import AppointmentPhoto, ConversationState, User
from app.database.repositories import (
    AppointmentPhotoRepository,
    AppointmentRepository,
    ConversationStateRepository,
)
from app.services.user_entry import BOOKING_FLOW
from app.services.vehicle_selection import VehicleSelectionError

MAX_PHOTOS = 10
STATE_TTL = timedelta(days=30)


class PhotoAddStatus(StrEnum):
    ADDED = "added"
    DUPLICATE = "duplicate"
    LIMIT = "limit"


@dataclass(slots=True, frozen=True)
class PhotoMetadata:
    file_id: str
    file_unique_id: str
    media_type: MediaType


@dataclass(slots=True, frozen=True)
class PhotoResult:
    status: PhotoAddStatus
    count: int


class PhotoUploadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.appointments = AppointmentRepository(session)
        self.photos = AppointmentPhotoRepository(session)
        self.states = ConversationStateRepository(session)

    async def add(self, user: User, metadata: PhotoMetadata) -> PhotoResult:
        state, appointment_id = await self._state_and_locked_draft(user)
        if await self.photos.exists(appointment_id, metadata.file_unique_id):
            count = await self.photos.count_for_appointment(appointment_id)
            return PhotoResult(PhotoAddStatus.DUPLICATE, count)
        count = await self.photos.count_for_appointment(appointment_id)
        if count >= MAX_PHOTOS:
            return PhotoResult(PhotoAddStatus.LIMIT, count)
        await self.photos.add(
            AppointmentPhoto(
                appointment_id=appointment_id,
                telegram_file_id=metadata.file_id,
                telegram_file_unique_id=metadata.file_unique_id,
                media_type=metadata.media_type,
            )
        )
        count += 1
        await self._save_state(state, "photo_upload", count)
        return PhotoResult(PhotoAddStatus.ADDED, count)

    async def remove_last(self, user: User) -> int:
        state, appointment_id = await self._state_and_locked_draft(user)
        photo = await self.photos.get_last(appointment_id)
        if photo is not None:
            await self.session.delete(photo)
            await self.session.flush()
        count = await self.photos.count_for_appointment(appointment_id)
        await self._save_state(state, "photo_upload", count)
        return count

    async def finish(self, user: User) -> ConversationState:
        state, appointment_id = await self._state_and_locked_draft(user)
        count = await self.photos.count_for_appointment(appointment_id)
        return await self._save_state(state, "date_selection", count)

    async def back(self, user: User) -> ConversationState:
        state, appointment_id = await self._state_and_locked_draft(user)
        count = await self.photos.count_for_appointment(appointment_id)
        return await self._save_state(state, "service_selection", count)

    async def count(self, user: User) -> int:
        _, appointment_id = await self._state_and_locked_draft(user)
        return await self.photos.count_for_appointment(appointment_id)

    async def _state_and_locked_draft(
        self, user: User
    ) -> tuple[ConversationState, UUID]:
        state = await self.states.get_active_for_flow(
            user.id, BOOKING_FLOW, datetime.now(UTC)
        )
        if state is None:
            raise VehicleSelectionError("Сценарий истёк. Начните заново.")
        if state.step != "photo_upload":
            raise VehicleSelectionError(
                "Загрузка фотографий уже завершена. Продолжите с текущего шага."
            )
        try:
            appointment_id = UUID(str(state.payload.get("appointment_id")))
        except (TypeError, ValueError) as error:
            raise VehicleSelectionError("Сохранённые данные повреждены.") from error
        appointment = await self.appointments.get_owned_draft_for_update(
            appointment_id, user.id
        )
        if appointment is None:
            raise VehicleSelectionError("Черновик уже закрыт.")
        return state, appointment_id

    async def _save_state(
        self, state: ConversationState, step: str, count: int
    ) -> ConversationState:
        payload = dict(state.payload)
        payload["photo_count"] = count
        return await self.states.upsert(
            user_id=state.user_id,
            flow=state.flow,
            step=step,
            payload=payload,
            expires_at=datetime.now(UTC) + STATE_TTL,
        )
