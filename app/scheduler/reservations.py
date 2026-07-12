"""Periodic expiration of temporary slot reservations without Redis."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.enums import AppointmentStatus, ReservationStatus
from app.database.models import (
    Appointment,
    AppointmentSlotReservation,
    AvailableSlot,
    ConversationState,
)
from app.services.user_entry import BOOKING_FLOW

logger = logging.getLogger(__name__)


async def expire_reservations_once(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 100
) -> int:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    result = await session.execute(
        select(AppointmentSlotReservation)
        .where(
            AppointmentSlotReservation.status == ReservationStatus.ACTIVE,
            AppointmentSlotReservation.reserved_until <= current,
        )
        .order_by(AppointmentSlotReservation.reserved_until)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    reservations = list(result.scalars())
    for reservation in reservations:
        # Recheck after acquiring the row lock.
        if (
            reservation.status != ReservationStatus.ACTIVE
            or reservation.reserved_until is None
            or reservation.reserved_until > current
        ):
            continue
        reservation.status = ReservationStatus.EXPIRED
        appointment = await session.get(
            Appointment, reservation.appointment_id, with_for_update=True
        )
        slot = await session.get(
            AvailableSlot, reservation.slot_id, with_for_update=True
        )
        if slot is not None and slot.blocked_reason is None:
            slot.is_available = slot.starts_at > current
        if (
            appointment is not None
            and appointment.status == AppointmentStatus.DRAFT
            and appointment.slot_id == reservation.slot_id
        ):
            appointment.slot_id = None
            appointment.scheduled_at = None
            state_result = await session.execute(
                select(ConversationState)
                .where(
                    ConversationState.user_id == appointment.user_id,
                    ConversationState.flow == BOOKING_FLOW,
                )
                .with_for_update()
            )
            state = state_result.scalar_one_or_none()
            if state is not None:
                payload = dict(state.payload)
                for key in ("slot_id", "scheduled_at", "reserved_until"):
                    payload.pop(key, None)
                state.payload = payload
                if state.step == "contact_name":
                    state.step = "date_selection"
                state.expires_at = current + timedelta(days=30)
    await session.flush()
    return len(reservations)


async def reservation_cleanup_loop(
    session_factory: async_sessionmaker[AsyncSession],
    stop_event: asyncio.Event,
    *,
    interval_seconds: int,
) -> None:
    logger.info(
        "Reservation cleanup worker started; interval_seconds=%s",
        interval_seconds,
    )
    while not stop_event.is_set():
        try:
            async with session_factory() as session:
                async with session.begin():
                    expired = await expire_reservations_once(session)
            if expired:
                logger.info("Expired slot reservations released; count=%s", expired)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reservation cleanup iteration failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
    logger.info("Reservation cleanup worker stopped")
