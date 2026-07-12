"""Database-backed appointment summary projection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Appointment,
    AvailableSlot,
    Service,
    User,
    VehicleBrand,
    VehicleClass,
    VehicleModel,
)
from app.database.repositories import AppointmentPhotoRepository, AppointmentRepository
from app.services.vehicle_selection import VehicleSelectionError


@dataclass(slots=True, frozen=True)
class AppointmentSummary:
    appointment: Appointment
    user: User
    vehicle: str
    vehicle_class: str | None
    service_name: str
    slot: AvailableSlot
    photo_count: int
    price_from: Decimal | None
    price_to: Decimal | None


class ApplicationSummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.appointments = AppointmentRepository(session)
        self.photos = AppointmentPhotoRepository(session)

    async def for_draft(self, user: User) -> AppointmentSummary:
        appointment = await self.appointments.get_draft_for_user(user.id)
        if appointment is None:
            raise VehicleSelectionError("Черновик не найден.")
        return await self._build(appointment, user)

    async def for_appointment(
        self, appointment: Appointment, user: User
    ) -> AppointmentSummary:
        return await self._build(appointment, user)

    async def _build(self, appointment: Appointment, user: User) -> AppointmentSummary:
        brand = (
            await self.session.get(VehicleBrand, appointment.vehicle_brand_id)
            if appointment.vehicle_brand_id
            else None
        )
        model = (
            await self.session.get(VehicleModel, appointment.vehicle_model_id)
            if appointment.vehicle_model_id
            else None
        )
        vehicle_class = (
            await self.session.get(VehicleClass, appointment.vehicle_class_id)
            if appointment.vehicle_class_id
            else None
        )
        service = (
            await self.session.get(Service, appointment.service_id)
            if appointment.service_id
            else None
        )
        slot = (
            await self.session.get(AvailableSlot, appointment.slot_id)
            if appointment.slot_id
            else None
        )
        if service is None or slot is None:
            raise VehicleSelectionError("Заявка заполнена не полностью.")
        brand_name = brand.name if brand else appointment.custom_vehicle_brand
        model_name = model.name if model else appointment.custom_vehicle_model
        vehicle = (
            " ".join(part for part in (brand_name, model_name) if part) or "Не указан"
        )
        return AppointmentSummary(
            appointment=appointment,
            user=user,
            vehicle=vehicle,
            vehicle_class=vehicle_class.name if vehicle_class else None,
            service_name=service.name,
            slot=slot,
            photo_count=await self.photos.count_for_appointment(appointment.id),
            price_from=appointment.estimated_price_from,
            price_to=appointment.estimated_price_to,
        )
