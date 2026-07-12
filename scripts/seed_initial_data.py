"""Idempotently insert the minimum editable catalog and content defaults."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_database_settings  # noqa: E402
from app.database.models import ContentSetting, Service, VehicleClass  # noqa: E402
from app.database.session import create_database  # noqa: E402


VEHICLE_CLASSES = (
    ("Компактный", Decimal("1.0000"), 10),
    ("Средний", Decimal("1.1500"), 20),
    ("Кроссовер / внедорожник", Decimal("1.3000"), 30),
    ("Минивэн / большой внедорожник", Decimal("1.5000"), 40),
)
SERVICES = (
    (
        "Бесплатный осмотр",
        "Осмотр автомобиля и консультация",
        Decimal("0.00"),
        30,
        True,
        10,
    ),
    (
        "Комплексная мойка",
        "Мойка кузова и уборка салона",
        Decimal("2500.00"),
        120,
        False,
        20,
    ),
    (
        "Химчистка салона",
        "Предварительная цена уточняется после осмотра",
        Decimal("8000.00"),
        360,
        False,
        30,
    ),
    (
        "Полировка кузова",
        "Предварительная цена уточняется после осмотра",
        Decimal("12000.00"),
        480,
        False,
        40,
    ),
)
CONTENT = {
    "welcome_text": "Добро пожаловать в детейлинг-студию! Выберите нужный раздел.",
    "studio_description": "Профессиональный уход за автомобилем.",
    "studio_address": "Укажите адрес в административной панели.",
    "studio_phone": "Укажите телефон в административной панели.",
    "manager_telegram": "Укажите Telegram менеджера в административной панели.",
    "working_hours": "Укажите режим работы в административной панели.",
    "application_sent_message": "Заявка отправлена. Мы свяжемся с вами после проверки.",
    "confirmation_message": "Ваша запись подтверждена.",
    "cancellation_rules": "Условия отмены уточняйте у менеджера.",
    "reminder_hours": "24,2",
    "calculator_description": "Расчёт является предварительным и уточняется после осмотра.",
}


async def seed() -> dict[str, int]:
    database = create_database(get_database_settings())
    counts = {"vehicle_classes": 0, "services": 0, "content_settings": 0}
    try:
        async with database.session_factory() as session:
            async with session.begin():
                for name, coefficient, sort_order in VEHICLE_CLASSES:
                    existing = await session.scalar(
                        select(VehicleClass).where(VehicleClass.name == name)
                    )
                    if existing is None:
                        session.add(
                            VehicleClass(
                                name=name,
                                price_coefficient=coefficient,
                                sort_order=sort_order,
                            )
                        )
                        counts["vehicle_classes"] += 1
                for name, description, price, duration, free, sort_order in SERVICES:
                    existing = await session.scalar(
                        select(Service).where(Service.name == name)
                    )
                    if existing is None:
                        session.add(
                            Service(
                                name=name,
                                short_description=description,
                                base_price=price,
                                duration_minutes=duration,
                                is_free_inspection=free,
                                sort_order=sort_order,
                            )
                        )
                        counts["services"] += 1
                for key, value in CONTENT.items():
                    existing = await session.scalar(
                        select(ContentSetting).where(ContentSetting.key == key)
                    )
                    if existing is None:
                        session.add(ContentSetting(key=key, value=value))
                        counts["content_settings"] += 1
    finally:
        await database.dispose()
    return counts


def run() -> None:
    try:
        counts = asyncio.run(seed())
    except Exception as error:
        print(
            f"Initial data seed failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    print(
        "Initial data ready; inserted "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
        + "."
    )


if __name__ == "__main__":
    run()
