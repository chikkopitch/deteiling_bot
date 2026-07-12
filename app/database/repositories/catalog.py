"""Vehicle and service catalog repositories."""

from uuid import UUID

from sqlalchemy import func, select

from app.database.models import (
    Service,
    ServicePrice,
    VehicleBrand,
    VehicleClass,
    VehicleModel,
)
from app.database.repositories.base import BaseRepository


class VehicleClassRepository(BaseRepository[VehicleClass]):
    model = VehicleClass

    async def list_active(self) -> list[VehicleClass]:
        result = await self.session.execute(
            select(VehicleClass)
            .where(VehicleClass.is_active.is_(True))
            .order_by(VehicleClass.sort_order, VehicleClass.name)
        )
        return list(result.scalars())


class VehicleBrandRepository(BaseRepository[VehicleBrand]):
    model = VehicleBrand

    async def list_active(self) -> list[VehicleBrand]:
        result = await self.session.execute(
            select(VehicleBrand)
            .where(VehicleBrand.is_active.is_(True))
            .order_by(VehicleBrand.sort_order, VehicleBrand.name)
        )
        return list(result.scalars())

    async def list_page(
        self, *, offset: int, limit: int, search: str | None = None
    ) -> tuple[list[VehicleBrand], int]:
        conditions = [VehicleBrand.is_active.is_(True)]
        if search:
            conditions.append(VehicleBrand.name.icontains(search, autoescape=True))
        total = await self.session.scalar(
            select(func.count()).select_from(VehicleBrand).where(*conditions)
        )
        result = await self.session.execute(
            select(VehicleBrand)
            .where(*conditions)
            .order_by(VehicleBrand.sort_order, VehicleBrand.name)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars()), int(total or 0)

    async def get_active(self, brand_id: UUID) -> VehicleBrand | None:
        result = await self.session.execute(
            select(VehicleBrand).where(
                VehicleBrand.id == brand_id,
                VehicleBrand.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


class VehicleModelRepository(BaseRepository[VehicleModel]):
    model = VehicleModel

    async def list_active_for_brand(self, brand_id: UUID) -> list[VehicleModel]:
        result = await self.session.execute(
            select(VehicleModel)
            .where(
                VehicleModel.brand_id == brand_id,
                VehicleModel.is_active.is_(True),
            )
            .order_by(VehicleModel.sort_order, VehicleModel.name)
        )
        return list(result.scalars())

    async def list_page_for_brand(
        self,
        brand_id: UUID,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
    ) -> tuple[list[VehicleModel], int]:
        conditions = [
            VehicleModel.brand_id == brand_id,
            VehicleModel.is_active.is_(True),
        ]
        if search:
            conditions.append(VehicleModel.name.icontains(search, autoescape=True))
        total = await self.session.scalar(
            select(func.count()).select_from(VehicleModel).where(*conditions)
        )
        result = await self.session.execute(
            select(VehicleModel)
            .where(*conditions)
            .order_by(VehicleModel.sort_order, VehicleModel.name)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars()), int(total or 0)

    async def get_active_for_brand(
        self, model_id: UUID, brand_id: UUID
    ) -> VehicleModel | None:
        result = await self.session.execute(
            select(VehicleModel).where(
                VehicleModel.id == model_id,
                VehicleModel.brand_id == brand_id,
                VehicleModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


class ServiceRepository(BaseRepository[Service]):
    model = Service

    async def list_active(self) -> list[Service]:
        result = await self.session.execute(
            select(Service)
            .where(Service.is_active.is_(True))
            .order_by(Service.sort_order, Service.name)
        )
        return list(result.scalars())

    async def get_price(
        self, service_id: UUID, vehicle_class_id: UUID
    ) -> ServicePrice | None:
        result = await self.session.execute(
            select(ServicePrice).where(
                ServicePrice.service_id == service_id,
                ServicePrice.vehicle_class_id == vehicle_class_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_page(self, *, offset: int, limit: int) -> tuple[list[Service], int]:
        condition = Service.is_active.is_(True)
        total = await self.session.scalar(
            select(func.count()).select_from(Service).where(condition)
        )
        result = await self.session.execute(
            select(Service)
            .where(condition)
            .order_by(Service.sort_order, Service.name)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars()), int(total or 0)

    async def get_active(self, service_id: UUID) -> Service | None:
        result = await self.session.execute(
            select(Service).where(
                Service.id == service_id,
                Service.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_free_inspection(self) -> Service | None:
        result = await self.session.execute(
            select(Service)
            .where(
                Service.is_active.is_(True),
                Service.is_free_inspection.is_(True),
            )
            .order_by(Service.sort_order, Service.name)
            .limit(1)
        )
        return result.scalar_one_or_none()
