from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FAQItem, PriceRule, Service, ServiceCategory, VehicleBrand, VehicleModel
from app.repositories.base import Repository


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def brands(
        self, query: str | None = None, limit: int = 12, offset: int = 0
    ) -> list[VehicleBrand]:
        stmt = (
            select(VehicleBrand)
            .where(VehicleBrand.is_active)
            .order_by(VehicleBrand.is_popular.desc(), VehicleBrand.name)
            .limit(limit)
            .offset(offset)
        )
        if query:
            stmt = stmt.where(VehicleBrand.name.ilike(f"%{query.strip()}%"))
        return list(await self.session.scalars(stmt))

    async def models(self, brand_id: UUID, limit: int = 12, offset: int = 0) -> list[VehicleModel]:
        return list(
            await self.session.scalars(
                select(VehicleModel)
                .where(VehicleModel.brand_id == brand_id, VehicleModel.is_active)
                .order_by(VehicleModel.name)
                .limit(limit)
                .offset(offset)
            )
        )

    async def services(
        self, limit: int = 10, offset: int = 0, category_id: UUID | None = None
    ) -> list[Service]:
        statement = (
            select(Service)
            .join(ServiceCategory)
            .where(Service.is_active, Service.deleted_at.is_(None), ServiceCategory.is_active)
            .order_by(ServiceCategory.sort_order, Service.sort_order)
            .limit(limit)
            .offset(offset)
        )
        if category_id:
            statement = statement.where(Service.category_id == category_id)
        return list(await self.session.scalars(statement))

    async def service_categories(self) -> list[ServiceCategory]:
        return list(
            await self.session.scalars(
                select(ServiceCategory)
                .where(ServiceCategory.is_active)
                .order_by(ServiceCategory.sort_order)
            )
        )

    async def faq_categories(self) -> list[str]:
        rows = await self.session.scalars(
            select(FAQItem.category)
            .where(FAQItem.is_active, FAQItem.deleted_at.is_(None))
            .distinct()
            .order_by(FAQItem.category)
        )
        return list(rows)

    async def faq(
        self,
        category: str | None = None,
        query: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[FAQItem]:
        stmt = (
            select(FAQItem)
            .where(FAQItem.is_active, FAQItem.deleted_at.is_(None))
            .order_by(FAQItem.sort_order)
            .limit(limit)
            .offset(offset)
        )
        if category:
            stmt = stmt.where(FAQItem.category == category)
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    FAQItem.question.ilike(pattern),
                    FAQItem.answer.ilike(pattern),
                    FAQItem.keywords.ilike(pattern),
                )
            )
        return list(await self.session.scalars(stmt))

    async def price_rule(self, service_id: UUID, vehicle_class: str) -> PriceRule | None:
        return await self.session.scalar(
            select(PriceRule).where(
                PriceRule.service_id == service_id,
                PriceRule.vehicle_class == vehicle_class,
                PriceRule.is_active,
            )
        )


class ServiceRepository(Repository[Service]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Service)
