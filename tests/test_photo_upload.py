from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.bot.handlers.services import photo_metadata_from_message
from app.database.enums import MediaType
from app.database.models import AppointmentPhoto, ConversationState, User
from app.services.photo_upload import (
    MAX_PHOTOS,
    PhotoAddStatus,
    PhotoMetadata,
    PhotoUploadService,
)

pytestmark = pytest.mark.asyncio


def _user() -> User:
    return User(id=uuid4(), telegram_id=808080)


def _state(user: User, appointment_id) -> ConversationState:
    return ConversationState(
        id=uuid4(),
        user_id=user.id,
        flow="booking",
        step="photo_upload",
        payload={"appointment_id": str(appointment_id)},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


async def test_upload_photo_uses_largest_telegram_size() -> None:
    message = SimpleNamespace(
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="same"),
            SimpleNamespace(file_id="large", file_unique_id="same"),
        ],
        document=None,
    )

    metadata = photo_metadata_from_message(message)

    assert metadata == PhotoMetadata("large", "same", MediaType.PHOTO)


async def test_upload_image_document_is_accepted_without_download() -> None:
    message = SimpleNamespace(
        photo=None,
        document=SimpleNamespace(
            file_id="document-id",
            file_unique_id="document-unique",
            mime_type="image/png",
        ),
    )

    metadata = photo_metadata_from_message(message)

    assert metadata == PhotoMetadata(
        "document-id", "document-unique", MediaType.DOCUMENT
    )


async def test_duplicate_photo_is_not_inserted() -> None:
    user = _user()
    appointment_id = uuid4()
    service = PhotoUploadService(AsyncMock())
    service._state_and_locked_draft = AsyncMock(
        return_value=(_state(user, appointment_id), appointment_id)
    )
    service.photos.exists = AsyncMock(return_value=True)
    service.photos.count_for_appointment = AsyncMock(return_value=3)
    service.photos.add = AsyncMock()

    result = await service.add(
        user, PhotoMetadata("file", "duplicate", MediaType.PHOTO)
    )

    assert result.status == PhotoAddStatus.DUPLICATE
    assert result.count == 3
    service.photos.add.assert_not_awaited()


async def test_new_photo_metadata_is_inserted() -> None:
    user = _user()
    appointment_id = uuid4()
    state = _state(user, appointment_id)
    service = PhotoUploadService(AsyncMock())
    service._state_and_locked_draft = AsyncMock(return_value=(state, appointment_id))
    service.photos.exists = AsyncMock(return_value=False)
    service.photos.count_for_appointment = AsyncMock(return_value=2)
    service.photos.add = AsyncMock()
    service._save_state = AsyncMock(return_value=state)

    result = await service.add(
        user, PhotoMetadata("new-file", "new-unique", MediaType.PHOTO)
    )

    assert result.status == PhotoAddStatus.ADDED
    assert result.count == 3
    saved = service.photos.add.await_args.args[0]
    assert saved.telegram_file_id == "new-file"
    assert saved.telegram_file_unique_id == "new-unique"
    service._save_state.assert_awaited_once_with(state, "photo_upload", 3)


async def test_photo_over_limit_is_not_inserted() -> None:
    user = _user()
    appointment_id = uuid4()
    service = PhotoUploadService(AsyncMock())
    service._state_and_locked_draft = AsyncMock(
        return_value=(_state(user, appointment_id), appointment_id)
    )
    service.photos.exists = AsyncMock(return_value=False)
    service.photos.count_for_appointment = AsyncMock(return_value=MAX_PHOTOS)
    service.photos.add = AsyncMock()

    result = await service.add(
        user, PhotoMetadata("file-11", "unique-11", MediaType.PHOTO)
    )

    assert result.status == PhotoAddStatus.LIMIT
    assert result.count == MAX_PHOTOS
    service.photos.add.assert_not_awaited()


async def test_remove_last_photo() -> None:
    user = _user()
    appointment_id = uuid4()
    state = _state(user, appointment_id)
    photo = AppointmentPhoto(
        id=uuid4(),
        appointment_id=appointment_id,
        telegram_file_id="last",
        telegram_file_unique_id="last-unique",
        media_type=MediaType.PHOTO,
    )
    session = AsyncMock()
    service = PhotoUploadService(session)
    service._state_and_locked_draft = AsyncMock(return_value=(state, appointment_id))
    service.photos.get_last = AsyncMock(return_value=photo)
    service.photos.count_for_appointment = AsyncMock(return_value=2)
    service._save_state = AsyncMock(return_value=state)

    count = await service.remove_last(user)

    assert count == 2
    session.delete.assert_awaited_once_with(photo)
    service._save_state.assert_awaited_once_with(state, "photo_upload", 2)


async def test_skip_photos_moves_to_date_selection() -> None:
    user = _user()
    appointment_id = uuid4()
    state = _state(user, appointment_id)
    service = PhotoUploadService(AsyncMock())
    service._state_and_locked_draft = AsyncMock(return_value=(state, appointment_id))
    service.photos.count_for_appointment = AsyncMock(return_value=0)
    service._save_state = AsyncMock(return_value=state)

    await service.finish(user)

    service._save_state.assert_awaited_once_with(state, "date_selection", 0)
