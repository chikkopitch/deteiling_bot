"""PostgreSQL-backed reminder queue worker without Redis."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.database.enums import ReminderStatus
from app.database.models import Appointment, Reminder, User
from app.database.repositories import ReminderRepository
from app.services.client_notifications import ClientNotificationService

logger = logging.getLogger(__name__)


async def acquire_due_reminders(
    session: AsyncSession, *, now: datetime, limit: int = 100
) -> list[UUID]:
    reminders = await ReminderRepository(session).acquire_due(now, limit)
    for reminder in reminders:
        reminder.status = ReminderStatus.PROCESSING
        reminder.processing_started_at = now
        reminder.last_error = None
    await session.flush()
    return [reminder.id for reminder in reminders]


async def requeue_stuck_reminders(
    session: AsyncSession,
    *,
    now: datetime,
    timeout_minutes: int,
    max_attempts: int,
    limit: int = 100,
) -> int:
    threshold = now - timedelta(minutes=timeout_minutes)
    result = await session.execute(
        select(Reminder)
        .where(
            Reminder.status == ReminderStatus.PROCESSING,
            Reminder.processing_started_at <= threshold,
        )
        .order_by(Reminder.processing_started_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    reminders = list(result.scalars())
    for reminder in reminders:
        reminder.attempts += 1
        reminder.processing_started_at = None
        reminder.last_error = "Processing timeout"
        reminder.status = (
            ReminderStatus.FAILED
            if reminder.attempts >= max_attempts
            else ReminderStatus.PENDING
        )
    await session.flush()
    return len(reminders)


async def _mark_delivery_result(
    session_factory: async_sessionmaker[AsyncSession],
    reminder_id: UUID,
    *,
    success: bool,
    error: Exception | None,
    settings: Settings,
    now: datetime,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(Reminder).where(Reminder.id == reminder_id).with_for_update()
            )
            reminder = result.scalar_one_or_none()
            if reminder is None or reminder.status != ReminderStatus.PROCESSING:
                return
            reminder.processing_started_at = None
            if success:
                reminder.status = ReminderStatus.SENT
                reminder.sent_at = now
                reminder.last_error = None
            else:
                reminder.attempts += 1
                safe_error = (
                    f"{type(error).__name__}: {error}"
                    if error is not None
                    else "Unknown error"
                )
                reminder.last_error = safe_error[:1000]
                reminder.status = (
                    ReminderStatus.FAILED
                    if reminder.attempts >= settings.reminder_max_attempts
                    else ReminderStatus.PENDING
                )


async def deliver_reminder(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    settings: Settings,
    reminder_id: UUID,
) -> None:
    error: Exception | None = None
    success = False
    try:
        async with session_factory() as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is None or reminder.status != ReminderStatus.PROCESSING:
                return
            appointment = await session.get(Appointment, reminder.appointment_id)
            if appointment is None:
                raise RuntimeError("Reminder appointment not found")
            user = await session.get(User, appointment.user_id)
            if user is None:
                raise RuntimeError("Reminder user not found")
            await ClientNotificationService(session, bot, settings).send_reminder(
                appointment, user
            )
            success = True
    except asyncio.CancelledError:
        raise
    except Exception as caught:
        error = caught
        logger.warning(
            "Reminder delivery failed; reminder_id=%s", reminder_id, exc_info=True
        )

    await _mark_delivery_result(
        session_factory,
        reminder_id,
        success=success,
        error=error,
        settings=settings,
        now=datetime.now(UTC),
    )


async def reminder_scheduler_loop(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    settings: Settings,
    stop_event: asyncio.Event,
) -> None:
    logger.info(
        "Reminder scheduler started; interval_seconds=%s",
        settings.reminder_check_interval_seconds,
    )
    while not stop_event.is_set():
        now = datetime.now(UTC)
        try:
            async with session_factory() as session:
                async with session.begin():
                    await requeue_stuck_reminders(
                        session,
                        now=now,
                        timeout_minutes=settings.reminder_processing_timeout_minutes,
                        max_attempts=settings.reminder_max_attempts,
                    )
                    reminder_ids = await acquire_due_reminders(session, now=now)
            for reminder_id in reminder_ids:
                await deliver_reminder(session_factory, bot, settings, reminder_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reminder scheduler iteration failed")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.reminder_check_interval_seconds,
            )
        except TimeoutError:
            continue
    logger.info("Reminder scheduler stopped")
