import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.database.enums import ReminderStatus
from app.database.models import Appointment, Reminder, User
from app.scheduler.reminders import (
    acquire_due_reminders,
    deliver_reminder,
    reminder_scheduler_loop,
    requeue_stuck_reminders,
)

pytestmark = pytest.mark.asyncio


def _settings() -> Settings:
    return Settings(
        bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        database_url="postgresql+asyncpg://u:p@localhost/test",
        owner_telegram_id=1,
    )


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


async def test_acquire_due_marks_processing() -> None:
    now = datetime.now(UTC)
    reminder = Reminder(
        id=uuid4(), appointment_id=uuid4(), reminder_type="before_2h", scheduled_for=now
    )
    session = AsyncMock()
    with patch(
        "app.scheduler.reminders.ReminderRepository.acquire_due",
        new=AsyncMock(return_value=[reminder]),
    ):
        ids = await acquire_due_reminders(session, now=now)
    assert ids == [reminder.id]
    assert reminder.status == ReminderStatus.PROCESSING
    assert reminder.processing_started_at == now


async def test_stuck_processing_is_retried_then_failed() -> None:
    now = datetime.now(UTC)
    reminder = Reminder(
        id=uuid4(),
        appointment_id=uuid4(),
        reminder_type="before_2h",
        scheduled_for=now,
        status=ReminderStatus.PROCESSING,
        attempts=0,
        processing_started_at=now - timedelta(minutes=11),
    )
    result = MagicMock()
    result.scalars.return_value = [reminder]
    session = AsyncMock()
    session.execute.return_value = result
    count = await requeue_stuck_reminders(
        session, now=now, timeout_minutes=10, max_attempts=2
    )
    assert count == 1
    assert reminder.status == ReminderStatus.PENDING
    assert reminder.attempts == 1

    reminder.status = ReminderStatus.PROCESSING
    reminder.processing_started_at = now - timedelta(minutes=11)
    await requeue_stuck_reminders(session, now=now, timeout_minutes=10, max_attempts=2)
    assert reminder.status == ReminderStatus.FAILED
    assert reminder.attempts == 2


@pytest.mark.parametrize(
    "send_error, success", [(None, True), (RuntimeError("Telegram error"), False)]
)
async def test_delivery_records_success_or_telegram_error(send_error, success) -> None:
    settings = _settings()
    reminder = Reminder(
        id=uuid4(),
        appointment_id=uuid4(),
        reminder_type="before_2h",
        scheduled_for=datetime.now(UTC),
        status=ReminderStatus.PROCESSING,
    )
    appointment = Appointment(id=reminder.appointment_id, user_id=uuid4())
    user = User(id=appointment.user_id, telegram_id=42)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[reminder, appointment, user])

    def factory() -> _SessionContext:
        return _SessionContext(session)

    send = AsyncMock(side_effect=send_error)
    mark = AsyncMock()
    with (
        patch(
            "app.scheduler.reminders.ClientNotificationService.send_reminder", new=send
        ),
        patch("app.scheduler.reminders._mark_delivery_result", new=mark),
    ):
        await deliver_reminder(factory, AsyncMock(), settings, reminder.id)
    assert mark.await_args.kwargs["success"] is success
    if success:
        assert mark.await_args.kwargs["error"] is None
    else:
        assert isinstance(mark.await_args.kwargs["error"], RuntimeError)


async def test_scheduler_starts_and_stops_without_redis() -> None:
    stop_event = asyncio.Event()
    stop_event.set()
    await reminder_scheduler_loop(AsyncMock(), AsyncMock(), _settings(), stop_event)
