"""Customer-facing appointment and reminder messages."""

from __future__ import annotations

from aiogram import Bot, html
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.appointment_actions import (
    customer_confirmed_keyboard,
    customer_rejected_keyboard,
)
from app.core.config import Settings
from app.database.models import Appointment, User
from app.database.repositories import ContentSettingRepository
from app.services.application_summary import ApplicationSummaryService


class ClientNotificationService:
    def __init__(self, session: AsyncSession, bot: Bot, settings: Settings) -> None:
        self.session = session
        self.bot = bot
        self.settings = settings
        self.content = ContentSettingRepository(session)

    async def send_confirmation(self, appointment: Appointment, user: User) -> None:
        summary = await ApplicationSummaryService(self.session).for_appointment(
            appointment, user
        )
        studio_name, address, phone, rules = await self._studio_content()
        visit = summary.slot.starts_at.astimezone(self.settings.app_timezone)
        await self.bot.send_message(
            user.telegram_id,
            f"<b>{html.quote(studio_name)}</b>\n\n"
            "Ваша запись подтверждена.\n"
            f"Услуга: {html.quote(summary.service_name)}\n"
            f"Автомобиль: {html.quote(summary.vehicle)}\n"
            f"Дата: {visit.strftime('%d.%m.%Y')}\n"
            f"Время: {visit.strftime('%H:%M')}\n"
            f"Адрес: {html.quote(address)}\n"
            f"Телефон студии: {html.quote(phone)}\n\n"
            f"Правила визита:\n{html.quote(rules)}",
            reply_markup=customer_confirmed_keyboard(appointment.id),
        )

    async def send_rejection(self, appointment: Appointment, user: User) -> None:
        await self.bot.send_message(
            user.telegram_id,
            "К сожалению, заявка отклонена.\n"
            f"Причина: {html.quote(appointment.rejection_reason or 'не указана')}\n\n"
            "Вы можете выбрать новое время или связаться с менеджером.",
            reply_markup=customer_rejected_keyboard(appointment.id),
        )

    async def send_reminder(self, appointment: Appointment, user: User) -> None:
        summary = await ApplicationSummaryService(self.session).for_appointment(
            appointment, user
        )
        studio_name, address, phone, rules = await self._studio_content()
        visit = summary.slot.starts_at.astimezone(self.settings.app_timezone)
        await self.bot.send_message(
            user.telegram_id,
            f"<b>Напоминание — {html.quote(studio_name)}</b>\n\n"
            f"Услуга: {html.quote(summary.service_name)}\n"
            f"Автомобиль: {html.quote(summary.vehicle)}\n"
            f"Дата и время: {visit.strftime('%d.%m.%Y %H:%M')}\n"
            f"Адрес: {html.quote(address)}\n"
            f"Телефон: {html.quote(phone)}\n\n"
            f"{html.quote(rules)}",
            reply_markup=customer_confirmed_keyboard(appointment.id),
        )

    async def _studio_content(self) -> tuple[str, str, str, str]:
        return (
            await self.content.get_value("studio_name", "Детейлинг-студия"),
            await self.content.get_value(
                "studio_address", "Адрес уточните у менеджера"
            ),
            await self.content.get_value(
                "studio_phone", "Телефон уточните у менеджера"
            ),
            await self.content.get_value(
                "visit_rules", "Пожалуйста, приезжайте к назначенному времени."
            ),
        )
