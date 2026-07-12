import asyncio
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.database import Database
from app.models import (
    FAQItem,
    PriceRule,
    Service,
    ServiceCategory,
    StudioSchedule,
    TimeSlot,
    VehicleBrand,
    VehicleModel,
)

BRANDS = {
    "BMW": ["3 серия", "5 серия", "X3", "X5"],
    "Mercedes-Benz": ["C-класс", "E-класс", "GLC", "GLE"],
    "Toyota": ["Camry", "Corolla", "RAV4", "Land Cruiser"],
    "Kia": ["Rio", "K5", "Sportage"],
    "Hyundai": ["Solaris", "Sonata", "Tucson"],
    "Lada": ["Vesta", "Granta", "Niva"],
}
SERVICES = [
    ("Защитные покрытия", "Керамическое покрытие", "Защита и глубокий блеск кузова", 720, 25000),
    (
        "Полировка",
        "Восстановительная полировка",
        "Убирает мелкие риски и возвращает блеск",
        480,
        18000,
    ),
    ("Химчистка", "Комплексная химчистка", "Глубокая очистка салона", 600, 15000),
    ("Мойка и уход", "Детейлинг-мойка", "Бережная очистка кузова и дисков", 180, 4500),
    ("Восстановление", "Восстановление фар", "Полировка и защита оптики", 180, 5000),
    ("Дополнительные услуги", "Антидождь", "Гидрофобное покрытие стёкол", 90, 3000),
    (
        "Защитные покрытия",
        "Оклейка полиуретановой плёнкой",
        "Защита уязвимых зон кузова",
        960,
        45000,
    ),
    ("Полировка", "Полировка одного элемента", "Локальное восстановление блеска", 120, 3500),
    ("Химчистка", "Химчистка сидений", "Глубокая очистка обивки", 180, 6000),
    (
        "Мойка и уход",
        "Консервация двигателя",
        "Бережная очистка и защита подкапотного пространства",
        120,
        4000,
    ),
]


async def seed() -> None:
    database = Database(get_settings().DATABASE_URL)
    async with database.session_factory() as session:
        if await session.scalar(select(VehicleBrand.id).limit(1)):
            await database.close()
            return
        for index, (brand_name, models) in enumerate(BRANDS.items()):
            brand = VehicleBrand(name=brand_name, is_popular=index < 5)
            session.add(brand)
            await session.flush()
            session.add_all([VehicleModel(brand_id=brand.id, name=name) for name in models])
        category_map: dict[str, ServiceCategory] = {}
        for order, (category_name, name, description, duration, price) in enumerate(SERVICES):
            category = category_map.get(category_name)
            if not category:
                category = ServiceCategory(name=category_name, sort_order=order)
                category_map[category_name] = category
                session.add(category)
                await session.flush()
            service = Service(
                category_id=category.id,
                name=name,
                short_description=description,
                duration_minutes=duration,
                price_from=Decimal(price),
                sort_order=order,
            )
            session.add(service)
            await session.flush()
            for vehicle_class, coefficient in (
                ("компакт", "0.9"),
                ("седан", "1"),
                ("кроссовер", "1.2"),
                ("внедорожник", "1.4"),
            ):
                session.add(
                    PriceRule(
                        service_id=service.id,
                        vehicle_class=vehicle_class,
                        base_price=Decimal(price),
                        class_coefficient=Decimal(coefficient),
                        condition_coefficients={
                            "лёгкое": 0.9,
                            "среднее": 1,
                            "сильное": 1.35,
                            "осмотр": 1,
                        },
                        options={"шерсть животных": 2000, "защитное покрытие": 5000},
                        min_price=Decimal(price) * Decimal("0.7"),
                        max_price=Decimal(price) * Decimal("2"),
                    )
                )
        session.add_all(
            [
                FAQItem(
                    category="запись",
                    question="Осмотр действительно бесплатный?",
                    answer="Да. Специалист оценит автомобиль и предложит подходящие варианты без обязательств.",
                    keywords="бесплатный осмотр",
                    sort_order=1,
                ),
                FAQItem(
                    category="сроки",
                    question="Сколько занимает работа?",
                    answer="Срок зависит от услуги и состояния автомобиля. Ориентир указан в каталоге, точный срок назовём после осмотра.",
                    keywords="время срок",
                    sort_order=2,
                ),
                FAQItem(
                    category="оплата",
                    question="Когда оплачивать работу?",
                    answer="Стоимость согласуем после осмотра, затем подберём удобный способ оплаты.",
                    keywords="оплата стоимость",
                    sort_order=3,
                ),
                FAQItem(
                    category="гарантии",
                    question="Есть ли гарантия на покрытие?",
                    answer="Гарантийные условия зависят от выбранного материала и фиксируются после осмотра.",
                    keywords="гарантия покрытие",
                    sort_order=4,
                ),
            ]
        )
        for weekday in range(7):
            session.add(
                StudioSchedule(
                    weekday=weekday, opens_at=time(9), closes_at=time(19), is_closed=weekday == 6
                )
            )
        start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        for day in range(14):
            for hour in range(9, 19):
                point = (start + timedelta(days=day)).replace(hour=hour)
                if point > datetime.now(UTC):
                    session.add(TimeSlot(starts_at=point, ends_at=point + timedelta(hours=1)))
        await session.commit()
    await database.close()


if __name__ == "__main__":
    asyncio.run(seed())
