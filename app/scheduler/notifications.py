from datetime import timedelta

import structlog
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot.keyboards.callbacks import BookingCallback, MenuCallback
from app.config import Settings
from app.database import Database
from app.models import (
    Booking,
    BookingStatus,
    Notification,
    NotificationStatus,
    NotificationType,
    User,
)
from app.repositories import NotificationRepository
from app.utils.datetime import format_studio_time, utc_now

log = structlog.get_logger()


class NotificationWorker:
    def __init__(
        self, database: Database, bot: Bot, settings: Settings, max_attempts: int = 4
    ) -> None:
        self.database, self.bot, self.settings, self.max_attempts = (
            database,
            bot,
            settings,
            max_attempts,
        )

    async def run(self) -> None:
        async with self.database.session_factory() as session:
            notifications = await NotificationRepository(session).due(utc_now())
            for note in notifications:
                booking = await session.scalar(
                    select(Booking)
                    .where(Booking.id == note.booking_id)
                    .options(selectinload(Booking.slot), selectinload(Booking.services))
                )
                user = await session.get(User, note.user_id)
                if (
                    not booking
                    or not user
                    or booking.status
                    in (
                        BookingStatus.CANCELLED_BY_CLIENT,
                        BookingStatus.CANCELLED_BY_ADMIN,
                    )
                ):
                    note.status = NotificationStatus.CANCELLED
                    continue
                try:
                    await self.bot.send_message(
                        user.telegram_id,
                        self._text(booking, note.type),
                        reply_markup=self._keyboard(),
                    )
                    note.status, note.sent_at, note.last_error = (
                        NotificationStatus.SENT,
                        utc_now(),
                        None,
                    )
                except TelegramRetryAfter as error:
                    self._retry(note, timedelta(seconds=error.retry_after), "flood_control")
                except TelegramNetworkError as error:
                    self._retry(note, None, type(error).__name__)
                except TelegramForbiddenError:
                    note.status, note.last_error = (
                        NotificationStatus.FAILED,
                        "bot_blocked_or_deleted",
                    )
                except TelegramBadRequest as error:
                    note.status, note.last_error = NotificationStatus.FAILED, type(error).__name__
            await session.commit()
            await log.ainfo("notification_batch", count=len(notifications))

    def _retry(self, notification: Notification, delay: timedelta | None, error: str) -> None:
        notification.attempts = (notification.attempts or 0) + 1
        if notification.attempts >= self.max_attempts:
            notification.status, notification.last_error = NotificationStatus.FAILED, error
            return
        notification.status = NotificationStatus.RETRY
        notification.scheduled_at = utc_now() + (
            delay or timedelta(minutes=2**notification.attempts)
        )
        notification.last_error = error

    def _text(self, booking: Booking, notification_type: NotificationType) -> str:
        if notification_type != NotificationType.REMINDER:
            return "Есть обновление по вашей записи. Откройте «Моя запись», чтобы увидеть детали."
        slot = booking.slot
        when = (
            format_studio_time(slot.starts_at, self.settings.STUDIO_TIMEZONE)
            if slot
            else "время уточняется"
        )
        services = ", ".join(item.name for item in booking.services) or "выбранные услуги"
        return (
            f"Напоминаем о визите: {when}.\n"
            f"Адрес: {self.settings.STUDIO_ADDRESS}\n"
            f"Услуги: {services}\nТелефон: {self.settings.SUPPORT_PHONE}"
        )

    def _keyboard(self) -> InlineKeyboardMarkup:
        rows = []
        if self.settings.MAP_URL:
            rows.append([InlineKeyboardButton(text="Построить маршрут", url=self.settings.MAP_URL)])
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="Моя запись", callback_data=MenuCallback(section="my_booking").pack()
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Перенести", callback_data=BookingCallback(action="reschedule").pack()
                    ),
                    InlineKeyboardButton(
                        text="Отменить",
                        callback_data=BookingCallback(action="cancel_booking").pack(),
                    ),
                ],
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)
