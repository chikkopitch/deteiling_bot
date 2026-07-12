from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FAQItem, Service, ServiceCategory, StudioSchedule, TimeSlot
from app.repositories import (
    CatalogRepository,
    FAQRepository,
    ScheduleRepository,
    ServiceCategoryRepository,
    UserRepository,
)


async def test_user_upsert_is_idempotent(session: AsyncSession) -> None:
    repo = UserRepository(session)
    first = await repo.upsert_telegram(42, "old", "A", None)
    second = await repo.upsert_telegram(42, "new", "B", "C")
    assert first.id == second.id and second.username == "new"


async def test_active_services_and_faq(session: AsyncSession) -> None:
    category = ServiceCategory(name="Полировка")
    session.add(category)
    await session.flush()
    session.add_all(
        [
            Service(
                category_id=category.id,
                name="Активная",
                short_description="x",
                duration_minutes=60,
                price_from=Decimal(1000),
            ),
            Service(
                category_id=category.id,
                name="Скрытая",
                short_description="x",
                duration_minutes=60,
                price_from=Decimal(1000),
                is_active=False,
            ),
            FAQItem(category="запись", question="Вопрос", answer="Ответ", sort_order=1),
        ]
    )
    await session.commit()
    catalog = CatalogRepository(session)
    assert [x.name for x in await catalog.services()] == ["Активная"]
    assert [x.question for x in await catalog.faq()] == ["Вопрос"]


async def test_slot_unique_start(session: AsyncSession) -> None:
    point = datetime.now(UTC) + timedelta(days=1)
    session.add(TimeSlot(starts_at=point, ends_at=point + timedelta(hours=1)))
    await session.commit()
    assert len(await CatalogRepository(session).brands()) == 0


async def test_content_and_schedule_repositories(session: AsyncSession) -> None:
    category = ServiceCategory(name="Care", sort_order=2)
    schedule = StudioSchedule(
        weekday=1, opens_at=datetime.min.time(), closes_at=datetime.max.time()
    )
    session.add_all(
        [category, schedule, FAQItem(category="booking", question="Q", answer="A", sort_order=1)]
    )
    await session.commit()

    assert [item.name for item in await ServiceCategoryRepository(session).active()] == ["Care"]
    assert [item.question for item in await FAQRepository(session).active("booking")] == ["Q"]
    assert len(await ScheduleRepository(session).for_weekday(1)) == 1
