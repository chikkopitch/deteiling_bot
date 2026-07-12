from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.booking import add_photo, delete_last_photo, photo_document


def settings(maximum: int = 2) -> SimpleNamespace:
    return SimpleNamespace(MAX_PHOTOS_PER_BOOKING=maximum, MAX_PHOTO_SIZE_MB=1)


@pytest.mark.asyncio
async def test_photo_is_saved_in_fsm_and_duplicate_is_rejected() -> None:
    state = SimpleNamespace(get_data=AsyncMock(return_value={}), update_data=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock())

    await add_photo(
        message,
        state,
        settings(),
        file_id="file-1",
        unique_file_id="unique-1",
        mime_type="image/jpeg",
        size_bytes=100,
    )

    saved = state.update_data.await_args.kwargs["photos"]
    assert saved[0]["file_id"] == "file-1"

    state.get_data = AsyncMock(return_value={"photos": saved})
    await add_photo(
        message,
        state,
        settings(),
        file_id="file-1-again",
        unique_file_id="unique-1",
        mime_type="image/jpeg",
        size_bytes=100,
    )
    assert "уже добавлено" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_photo_limit_and_size_are_enforced() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"photos": [{"unique_file_id": "first"}]}),
        update_data=AsyncMock(),
    )
    await add_photo(
        message,
        state,
        settings(maximum=1),
        file_id="file-2",
        unique_file_id="second",
        mime_type="image/jpeg",
        size_bytes=100,
    )
    assert "не больше" in message.answer.await_args.args[0]

    state.get_data = AsyncMock(return_value={})
    await add_photo(
        message,
        state,
        settings(),
        file_id="large",
        unique_file_id="large",
        mime_type="image/jpeg",
        size_bytes=2 * 1024 * 1024,
    )
    assert "не должен превышать" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_unsupported_document_and_delete_last_photo() -> None:
    message = SimpleNamespace(
        document=SimpleNamespace(mime_type="application/zip"), answer=AsyncMock()
    )
    await photo_document(message, SimpleNamespace(), settings())  # type: ignore[arg-type]
    assert "JPEG, PNG или WEBP" in message.answer.await_args.args[0]

    callback_message = SimpleNamespace(edit_text=AsyncMock())
    callback = SimpleNamespace(message=callback_message, answer=AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"photos": [{"unique_file_id": "first"}]}),
        update_data=AsyncMock(),
    )
    await delete_last_photo(callback, state)  # type: ignore[arg-type]
    assert state.update_data.await_args.kwargs["photos"] == []
