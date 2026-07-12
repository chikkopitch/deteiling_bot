"""Telegram delivery of a newly submitted application to active staff."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, html
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InputMediaDocument, InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.admin import admin_application_keyboard
from app.core.config import Settings
from app.database.enums import MediaType
from app.database.models import Appointment, User
from app.database.repositories import AdminRepository, AppointmentPhotoRepository
from app.services.application_summary import (
    ApplicationSummaryService,
    AppointmentSummary,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class DeliveryReport:
    delivered: int
    failed: int


def appointment_number(appointment: Appointment) -> str:
    return str(appointment.id).split("-")[0].upper()


def build_admin_application_text(
    summary: AppointmentSummary, settings: Settings
) -> str:
    appointment = summary.appointment
    user = summary.user
    visit = summary.slot.starts_at.astimezone(settings.app_timezone)
    created = appointment.created_at.astimezone(settings.app_timezone)
    username = f"@{user.username}" if user.username else "не указан"
    user_link = f'<a href="tg://user?id={user.telegram_id}">Открыть профиль</a>'
    price_from = appointment.estimated_price_from
    price_to = appointment.estimated_price_to
    price = (
        "не рассчитана"
        if price_from is None
        else f"{price_from}–{price_to or price_from} {settings.currency_symbol}"
    )
    return (
        f"<b>Новая заявка #{appointment_number(appointment)}</b>\n"
        f"Создана: {created.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Имя: {html.quote(appointment.customer_name or '')}\n"
        f"Телефон: {html.quote(appointment.customer_phone or '')}\n"
        f"Username: {html.quote(username)}\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"Пользователь: {user_link}\n\n"
        f"Автомобиль: {html.quote(summary.vehicle)}\n"
        f"Год: {appointment.vehicle_year or 'не указан'}\n"
        f"Услуга: {html.quote(summary.service_name)}\n"
        f"Дата визита: {visit.strftime('%d.%m.%Y')}\n"
        f"Время визита: {visit.strftime('%H:%M')}\n"
        f"Цена: {price}\n"
        f"Комментарий: {html.quote(appointment.vehicle_comment or 'нет')}\n"
        f"Фотографий: {summary.photo_count}"
    )


class AdminNotificationService:
    def __init__(self, session: AsyncSession, bot: Bot, settings: Settings) -> None:
        self.session = session
        self.bot = bot
        self.settings = settings
        self.admins = AdminRepository(session)
        self.photos = AppointmentPhotoRepository(session)

    async def notify_new_application(
        self, appointment: Appointment, user: User
    ) -> DeliveryReport:
        summary = await ApplicationSummaryService(self.session).for_appointment(
            appointment, user
        )
        text = build_admin_application_text(summary, self.settings)
        photos = await self.photos.list_for_appointment(appointment.id)
        admins = await self.admins.list_active()
        delivered = failed = 0
        for admin in admins:
            try:
                await self._send_files(admin.telegram_id, photos, appointment)
                await self.bot.send_message(
                    admin.telegram_id,
                    text,
                    reply_markup=admin_application_keyboard(appointment.id),
                )
                delivered += 1
            except TelegramAPIError:
                failed += 1
                logger.warning(
                    "Admin notification failed; admin_id=%s appointment_id=%s",
                    admin.id,
                    appointment.id,
                    exc_info=True,
                )
        return DeliveryReport(delivered=delivered, failed=failed)

    async def _send_files(
        self, chat_id: int, photos: list, appointment: Appointment
    ) -> None:
        photo_files = [item for item in photos if item.media_type == MediaType.PHOTO][
            :10
        ]
        document_files = [
            item for item in photos if item.media_type == MediaType.DOCUMENT
        ][:10]
        caption = f"Фотографии к заявке #{appointment_number(appointment)}"
        if len(photo_files) == 1:
            await self.bot.send_photo(
                chat_id, photo_files[0].telegram_file_id, caption=caption
            )
        elif len(photo_files) >= 2:
            media = [
                InputMediaPhoto(
                    media=item.telegram_file_id,
                    caption=caption if index == 0 else None,
                )
                for index, item in enumerate(photo_files)
            ]
            await self.bot.send_media_group(chat_id, media=media)
        if len(document_files) == 1:
            await self.bot.send_document(
                chat_id, document_files[0].telegram_file_id, caption=caption
            )
        elif len(document_files) >= 2:
            media = [
                InputMediaDocument(
                    media=item.telegram_file_id,
                    caption=caption if index == 0 else None,
                )
                for index, item in enumerate(document_files)
            ]
            await self.bot.send_media_group(chat_id, media=media)
