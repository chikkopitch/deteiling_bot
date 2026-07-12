from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.database.enums import (
    AdminRole,
    AppointmentStatus,
    MediaType,
    ReservationStatus,
    SenderType,
)
from app.database.models import (
    Admin,
    AdminAuditLog,
    Appointment,
    AppointmentHistory,
    AppointmentPhoto,
    AppointmentSlotReservation,
    AvailableSlot,
    ContentSetting,
    ConversationState,
    FAQItem,
    ManagerRequest,
    ManagerRequestMessage,
    Reminder,
    Service,
    ServicePrice,
    User,
    VehicleBrand,
    VehicleClass,
    VehicleModel,
)
from app.database.repositories import UserRepository

pytestmark = pytest.mark.asyncio


async def test_postgresql_connection_is_utc(postgres_engine: AsyncEngine) -> None:
    async with postgres_engine.connect() as connection:
        result = await connection.execute(text("SELECT 1, current_setting('TimeZone')"))
        value, timezone_name = result.one()

    assert value == 1
    assert timezone_name == "UTC"


async def test_create_main_records(postgres_session: AsyncSession) -> None:
    now = datetime.now(UTC).replace(microsecond=0)

    user = User(telegram_id=9_001_000_001, first_name="Тест")
    admin = Admin(telegram_id=9_001_000_002, role=AdminRole.OWNER)
    vehicle_class = VehicleClass(
        name="седан",
        price_coefficient=Decimal("1.1500"),
        sort_order=10,
    )
    brand = VehicleBrand(name="Test Brand", sort_order=10)
    service = Service(
        name="Тестовая услуга",
        short_description="Краткое описание",
        full_description="Полное описание",
        base_price=Decimal("1000.00"),
        duration_minutes=60,
    )
    slot = AvailableSlot(
        starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=1, hours=1)
    )
    postgres_session.add_all([user, admin, vehicle_class, brand, service, slot])
    await postgres_session.flush()

    vehicle_model = VehicleModel(
        brand_id=brand.id,
        vehicle_class_id=vehicle_class.id,
        name="Test Model",
    )
    service_price = ServicePrice(
        service_id=service.id,
        vehicle_class_id=vehicle_class.id,
        price=Decimal("1150.00"),
        min_price=Decimal("1100.00"),
        max_price=Decimal("1200.00"),
    )
    appointment = Appointment(
        user_id=user.id,
        service_id=service.id,
        vehicle_brand_id=brand.id,
        vehicle_class_id=vehicle_class.id,
        customer_name="Тестовый клиент",
        customer_phone="+79990000000",
        scheduled_at=slot.starts_at,
        estimated_price_from=Decimal("1100.00"),
        estimated_price_to=Decimal("1200.00"),
        status=AppointmentStatus.WAITING_ADMIN,
    )
    postgres_session.add_all([vehicle_model, service_price, appointment])
    await postgres_session.flush()
    appointment.vehicle_model_id = vehicle_model.id

    photo = AppointmentPhoto(
        appointment_id=appointment.id,
        telegram_file_id="telegram-file-id",
        telegram_file_unique_id="telegram-file-unique-id",
        media_type=MediaType.PHOTO,
    )
    reservation = AppointmentSlotReservation(
        appointment_id=appointment.id,
        slot_id=slot.id,
        reserved_until=now + timedelta(minutes=15),
        status=ReservationStatus.ACTIVE,
    )
    state = ConversationState(
        user_id=user.id,
        flow="booking",
        step="confirmation",
        payload={"appointment_id": str(appointment.id)},
        expires_at=now + timedelta(days=1),
    )
    reminder = Reminder(
        appointment_id=appointment.id,
        reminder_type="before_visit_24h",
        scheduled_for=slot.starts_at - timedelta(hours=24),
    )
    faq = FAQItem(question="Вопрос?", answer="Ответ", category="Общее")
    content = ContentSetting(key="welcome_text", value="Добро пожаловать")
    manager_request = ManagerRequest(
        user_id=user.id,
        appointment_id=appointment.id,
        topic="Запись",
        message="Нужна помощь",
        assigned_admin_id=admin.id,
    )
    postgres_session.add_all(
        [photo, reservation, state, reminder, faq, content, manager_request]
    )
    await postgres_session.flush()

    request_message = ManagerRequestMessage(
        request_id=manager_request.id,
        sender_type=SenderType.USER,
        sender_user_id=user.id,
        text="Сообщение клиента",
    )
    history = AppointmentHistory(
        appointment_id=appointment.id,
        action="created",
        new_value={"status": appointment.status.value},
        changed_by_user_id=user.id,
    )
    audit = AdminAuditLog(
        admin_id=admin.id,
        action="viewed",
        entity_type="appointment",
        entity_id=appointment.id,
        new_value={"status": appointment.status.value},
    )
    postgres_session.add_all([request_message, history, audit])
    await postgres_session.commit()

    loaded_user = await UserRepository(postgres_session).get_by_telegram_id(
        user.telegram_id
    )
    loaded_price = await postgres_session.scalar(
        select(ServicePrice).where(ServicePrice.id == service_price.id)
    )
    loaded_appointment = await postgres_session.get(Appointment, appointment.id)

    assert loaded_user is not None
    assert loaded_price is not None
    assert loaded_price.price == Decimal("1150.00")
    assert loaded_appointment is not None
    assert loaded_appointment.scheduled_at is not None
    assert loaded_appointment.scheduled_at.utcoffset() == timedelta(0)

    same_user = await UserRepository(postgres_session).upsert_telegram_profile(
        telegram_id=user.telegram_id,
        username="updated_username",
        first_name="Новое имя",
        last_name=None,
    )
    await postgres_session.commit()
    user_count = await postgres_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.telegram_id == user.telegram_id)
    )
    assert same_user.id == user.id
    assert user_count == 1
