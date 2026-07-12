from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FAQItem, ManagerRequest, ServiceCategory
from app.repositories.base import Repository


class ServiceCategoryRepository(Repository[ServiceCategory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ServiceCategory)

    async def active(self) -> list[ServiceCategory]:
        return list(
            await self.session.scalars(
                select(ServiceCategory)
                .where(ServiceCategory.is_active)
                .order_by(ServiceCategory.sort_order)
            )
        )


class FAQRepository(Repository[FAQItem]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FAQItem)

    async def active(self, category: str | None = None) -> list[FAQItem]:
        statement = (
            select(FAQItem)
            .where(FAQItem.is_active, FAQItem.deleted_at.is_(None))
            .order_by(FAQItem.sort_order)
        )
        if category:
            statement = statement.where(FAQItem.category == category)
        return list(await self.session.scalars(statement))


class ManagerRequestRepository(Repository[ManagerRequest]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ManagerRequest)

    async def open_for_user(self, user_id: UUID) -> list[ManagerRequest]:
        return list(
            await self.session.scalars(
                select(ManagerRequest)
                .where(ManagerRequest.user_id == user_id)
                .order_by(ManagerRequest.created_at.desc())
            )
        )
