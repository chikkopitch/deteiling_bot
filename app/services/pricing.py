from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import CatalogRepository
from app.schemas import PriceEstimate
from app.utils.datetime import utc_now


class PricingService:
    def __init__(self, session: AsyncSession) -> None:
        self.catalog = CatalogRepository(session)

    async def calculate(
        self, service_id: UUID, vehicle_class: str, condition: str, options: list[str]
    ) -> PriceEstimate:
        rule = await self.catalog.price_rule(service_id, vehicle_class)
        if rule is None:
            raise LookupError("Для выбранных параметров нужен бесплатный осмотр")
        condition_factor = Decimal(str(rule.condition_coefficients.get(condition, 1)))
        extras = sum((Decimal(str(rule.options.get(item, 0))) for item in options), Decimal(0))
        raw = rule.base_price * rule.class_coefficient * condition_factor + extras
        low = max(rule.min_price, raw * Decimal("0.90"))
        high = min(rule.max_price, raw * Decimal("1.15"))
        rounding = Decimal("100")
        low = (low / rounding).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * rounding
        high = (max(high, low) / rounding).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * rounding
        return PriceEstimate(
            minimum=low,
            maximum=high,
            factors=[f"класс: {vehicle_class}", f"состояние: {condition}", *options],
            calculated_at=utc_now(),
        )
