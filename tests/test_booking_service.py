from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingStatus,
    Service,
    ServiceCategory,
    SlotStatus,
    TimeSlot,
    User,
    Vehicle,
)
from app.schemas import BookingDraft, PhotoDraft
from app.services import BookingService, ensure_transition
from app.services.errors import InvalidTransitionError, SlotUnavailableError


def test_booking_state_machine() -> None:
    ensure_transition(BookingStatus.PENDING, BookingStatus.CONFIRMED)
    with pytest.raises(InvalidTransitionError):
        ensure_transition(BookingStatus.COMPLETED, BookingStatus.PENDING)


async def test_hold_prevents_second_user(session: AsyncSession) -> None:
    first = User(telegram_id=1, first_name="A")
    second = User(telegram_id=2, first_name="B")
    point = datetime.now(UTC) + timedelta(days=1)
    slot = TimeSlot(starts_at=point, ends_at=point + timedelta(hours=1))
    session.add_all([first, second, slot])
    await session.commit()
    service = BookingService(session)
    await service.hold_slot(slot.id, first, 10)
    await session.commit()
    with pytest.raises(SlotUnavailableError):
        await service.hold_slot(slot.id, second, 10)


async def test_submit_is_idempotent(session: AsyncSession) -> None:
    user = User(telegram_id=3, first_name="A")
    point = datetime.now(UTC) + timedelta(days=1)
    slot = TimeSlot(starts_at=point, ends_at=point + timedelta(hours=1))
    category = ServiceCategory(name="Care")
    session.add_all([user, slot, category])
    await session.flush()
    catalog_service = Service(
        category_id=category.id,
        name="Wash",
        short_description="x",
        duration_minutes=60,
        price_from=1000,
    )
    session.add(catalog_service)
    await session.commit()
    service = BookingService(session)
    await service.hold_slot(slot.id, user, 10)
    await session.commit()
    key = str(uuid4())
    draft = BookingDraft(
        brand="BMW",
        model="X5",
        year=2022,
        vehicle_class="кроссовер",
        service_ids=[catalog_service.id],
        slot_id=slot.id,
        customer_name="Иван",
        customer_phone="+79123456789",
        photos=[
            PhotoDraft(
                file_id="photo-file",
                unique_file_id="photo-unique",
                mime_type="image/jpeg",
                size_bytes=100,
            )
        ],
        idempotency_key=key,
    )
    first = await service.submit(user, draft)
    second = await service.submit(user, draft)
    assert (
        first.id == second.id
        and first.status == BookingStatus.PENDING
        and slot.status == SlotStatus.BOOKED
    )
    assert [item.id for item in first.services] == [catalog_service.id]


async def test_database_allows_only_one_active_booking_per_slot(session: AsyncSession) -> None:
    user = User(telegram_id=4, first_name="A")
    slot_time = datetime.now(UTC) + timedelta(days=2)
    slot = TimeSlot(starts_at=slot_time, ends_at=slot_time + timedelta(hours=1))
    session.add_all([user, slot])
    await session.flush()
    user_id, slot_id = user.id, slot.id
    first_vehicle = Vehicle(
        user_id=user.id,
        brand_name="BMW",
        model_name="X5",
        year=2022,
        vehicle_class="SUV",
    )
    second_vehicle = Vehicle(
        user_id=user.id,
        brand_name="BMW",
        model_name="X3",
        year=2021,
        vehicle_class="SUV",
    )
    session.add_all([first_vehicle, second_vehicle])
    await session.flush()
    first_vehicle_id, second_vehicle_id = first_vehicle.id, second_vehicle.id
    session.add(Booking(user_id=user_id, vehicle_id=first_vehicle_id, slot_id=slot_id))
    await session.commit()

    session.add(Booking(user_id=user_id, vehicle_id=second_vehicle_id, slot_id=slot_id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    first_booking = await session.scalar(select(Booking).where(Booking.slot_id == slot_id))
    assert first_booking is not None
    first_booking.status = BookingStatus.CANCELLED_BY_CLIENT
    await session.commit()
    session.add(Booking(user_id=user_id, vehicle_id=second_vehicle_id, slot_id=slot_id))
    await session.commit()


async def test_proposed_reschedule_replaces_slot_transactionally(session: AsyncSession) -> None:
    user = User(telegram_id=80, first_name="A")
    first_time = datetime.now(UTC) + timedelta(days=3)
    old_slot = TimeSlot(
        starts_at=first_time, ends_at=first_time + timedelta(hours=1), status=SlotStatus.BOOKED
    )
    new_slot = TimeSlot(
        starts_at=first_time + timedelta(hours=2), ends_at=first_time + timedelta(hours=3)
    )
    session.add_all([user, old_slot, new_slot])
    await session.flush()
    vehicle = Vehicle(
        user_id=user.id, brand_name="BMW", model_name="X5", year=2022, vehicle_class="SUV"
    )
    session.add(vehicle)
    await session.flush()
    booking = Booking(
        user_id=user.id,
        vehicle_id=vehicle.id,
        slot_id=old_slot.id,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    await session.commit()

    service = BookingService(session)
    offered = await service.propose_reschedule(booking.id, new_slot.id, user.id)
    assert offered.status == BookingStatus.RESCHEDULE_REQUESTED
    await session.refresh(new_slot)
    assert new_slot.status == SlotStatus.HELD and new_slot.held_by_user_id == user.id

    accepted = await service.accept_reschedule(booking.id, user.id)
    await session.refresh(old_slot)
    await session.refresh(new_slot)
    assert accepted.slot_id == new_slot.id
    assert old_slot.status == SlotStatus.AVAILABLE and new_slot.status == SlotStatus.BOOKED


async def test_client_reschedule_releases_old_slot(session: AsyncSession) -> None:
    user = User(telegram_id=81, first_name="A")
    starts_at = datetime.now(UTC) + timedelta(days=4)
    old_slot = TimeSlot(
        starts_at=starts_at, ends_at=starts_at + timedelta(hours=1), status=SlotStatus.BOOKED
    )
    new_slot = TimeSlot(
        starts_at=starts_at + timedelta(hours=2), ends_at=starts_at + timedelta(hours=3)
    )
    session.add_all([user, old_slot, new_slot])
    await session.flush()
    vehicle = Vehicle(
        user_id=user.id, brand_name="BMW", model_name="X5", year=2022, vehicle_class="SUV"
    )
    session.add(vehicle)
    await session.flush()
    booking = Booking(
        user_id=user.id, vehicle_id=vehicle.id, slot_id=old_slot.id, status=BookingStatus.CONFIRMED
    )
    session.add(booking)
    await session.commit()

    moved = await BookingService(session).reschedule_by_client(
        booking.id, user.id, new_slot.id, (24, 2), 2
    )
    await session.refresh(old_slot)
    await session.refresh(new_slot)
    assert moved.status == BookingStatus.CONFIRMED
    assert moved.slot_id == new_slot.id
    assert old_slot.status == SlotStatus.AVAILABLE and new_slot.status == SlotStatus.BOOKED
