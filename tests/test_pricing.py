from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceRule, Service, ServiceCategory
from app.services import PricingService


async def test_price_calculation_uses_database_rule(session: AsyncSession) -> None:
    category = ServiceCategory(name="Care")
    session.add(category)
    await session.flush()
    service = Service(
        category_id=category.id,
        name="Wash",
        short_description="x",
        duration_minutes=60,
        price_from=Decimal(1000),
    )
    session.add(service)
    await session.flush()
    session.add(
        PriceRule(
            service_id=service.id,
            vehicle_class="седан",
            base_price=Decimal(10000),
            class_coefficient=Decimal("1"),
            condition_coefficients={"среднее": 1.2},
            options={"защита": 1000},
            min_price=Decimal(5000),
            max_price=Decimal(30000),
        )
    )
    await session.commit()

    result = await PricingService(session).calculate(service.id, "седан", "среднее", ["защита"])

    assert result.minimum == Decimal(11700)
    assert result.maximum == Decimal(15000)
    assert "защита" in result.factors
