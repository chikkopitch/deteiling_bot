from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vehicle, VehicleBrand, VehicleModel
from app.repositories.base import Repository


class VehicleRepository(Repository[Vehicle]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Vehicle)

    async def for_user(self, user_id: UUID) -> list[Vehicle]:
        return list(
            await self.session.scalars(
                select(Vehicle)
                .where(Vehicle.user_id == user_id)
                .order_by(Vehicle.created_at.desc())
            )
        )


class VehicleBrandRepository(Repository[VehicleBrand]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VehicleBrand)

    async def by_name(self, name: str) -> VehicleBrand | None:
        return await self.session.scalar(select(VehicleBrand).where(VehicleBrand.name == name))


class VehicleModelRepository(Repository[VehicleModel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VehicleModel)

    async def for_brand(self, brand_id: UUID) -> list[VehicleModel]:
        return list(
            await self.session.scalars(
                select(VehicleModel)
                .where(VehicleModel.brand_id == brand_id, VehicleModel.is_active)
                .order_by(VehicleModel.name)
            )
        )
