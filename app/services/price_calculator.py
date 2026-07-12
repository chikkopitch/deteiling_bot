"""Decimal-only calculator driven by PostgreSQL factor rules."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    CalculationFactor,
    CalculationFactorValue,
    ConversationState,
    PriceCalculation,
    ServiceFactorCompatibility,
    User,
)
from app.database.repositories import ConversationStateRepository
from app.services.vehicle_selection import PRICE_FLOW, VehicleSelectionError

Q = Decimal("0.01")


def calculate_range(
    base_from: Decimal, base_to: Decimal, values
) -> tuple[Decimal, Decimal]:
    coefficient = Decimal("1")
    surcharge = Decimal("0")
    for value in values:
        coefficient *= Decimal(value.coefficient)
        surcharge += Decimal(value.fixed_surcharge)
    return (
        (base_from * coefficient + surcharge).quantize(Q, rounding=ROUND_HALF_UP),
        (base_to * coefficient + surcharge).quantize(Q, rounding=ROUND_HALF_UP),
    )


@dataclass(frozen=True, slots=True)
class FactorStep:
    factor: CalculationFactor
    values: list[CalculationFactorValue]
    index: int
    total: int


class PriceCalculatorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.states = ConversationStateRepository(session)

    async def factors(self, service_id: UUID) -> list[CalculationFactor]:
        result = await self.session.execute(
            select(CalculationFactor)
            .join(
                ServiceFactorCompatibility,
                ServiceFactorCompatibility.factor_id == CalculationFactor.id,
            )
            .where(
                ServiceFactorCompatibility.service_id == service_id,
                ServiceFactorCompatibility.is_active.is_(True),
                CalculationFactor.is_active.is_(True),
            )
            .order_by(CalculationFactor.sort_order, CalculationFactor.name)
        )
        return list(result.scalars())

    async def current_step(self, user: User) -> FactorStep | None:
        state = await self._state(user)
        factors = await self.factors(UUID(state.payload["service_id"]))
        index = int(state.payload.get("factor_index", 0))
        if index >= len(factors):
            return None
        factor = factors[index]
        result = await self.session.execute(
            select(CalculationFactorValue)
            .where(
                CalculationFactorValue.factor_id == factor.id,
                CalculationFactorValue.is_active.is_(True),
            )
            .order_by(CalculationFactorValue.sort_order, CalculationFactorValue.label)
        )
        return FactorStep(factor, list(result.scalars()), index, len(factors))

    async def select_value(self, user: User, value_id: UUID) -> ConversationState:
        state = await self._state(user)
        step = await self.current_step(user)
        if step is None:
            raise VehicleSelectionError("Расчёт уже завершён.")
        value = await self.session.get(CalculationFactorValue, value_id)
        if value is None or not value.is_active or value.factor_id != step.factor.id:
            raise VehicleSelectionError("Параметр больше недоступен.")
        selections = dict(state.payload.get("factor_selections", {}))
        if step.factor.input_type == "multiple":
            current = list(selections.get(step.factor.key, []))
            existing = next(
                (item for item in current if item["value_id"] == str(value.id)), None
            )
            if existing:
                current.remove(existing)
            else:
                current.append(
                    {
                        "value_id": str(value.id),
                        "label": value.label,
                        "factor_name": step.factor.name,
                    }
                )
            selections[step.factor.key] = current
        else:
            selections[step.factor.key] = [
                {
                    "value_id": str(value.id),
                    "label": value.label,
                    "factor_name": step.factor.name,
                }
            ]
        payload = dict(state.payload)
        payload.update(
            factor_selections=selections,
            factor_index=step.index + (step.factor.input_type != "multiple"),
        )
        return await self.states.upsert(
            user_id=user.id,
            flow=PRICE_FLOW,
            step="price_factors",
            payload=payload,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

    async def finish_multiple(self, user: User) -> ConversationState:
        state = await self._state(user)
        step = await self.current_step(user)
        if step is None or step.factor.input_type != "multiple":
            raise VehicleSelectionError("Этот параметр уже заполнен.")
        payload = dict(state.payload)
        payload["factor_index"] = step.index + 1
        return await self.states.upsert(
            user_id=user.id,
            flow=PRICE_FLOW,
            step="price_factors",
            payload=payload,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

    async def calculate(self, user: User) -> tuple[ConversationState, PriceCalculation]:
        state = await self._state(user)
        selected_ids = [
            UUID(item["value_id"])
            for items in state.payload.get("factor_selections", {}).values()
            for item in items
        ]
        values = []
        if selected_ids:
            result = await self.session.execute(
                select(CalculationFactorValue).where(
                    CalculationFactorValue.id.in_(selected_ids)
                )
            )
            values = list(result.scalars())
        base_from = Decimal(state.payload["estimated_price_from"])
        base_to = Decimal(state.payload["estimated_price_to"])
        result_from, result_to = calculate_range(base_from, base_to, values)
        calculation = PriceCalculation(
            user_id=user.id,
            service_id=UUID(state.payload["service_id"]),
            vehicle_class_id=UUID(state.payload["vehicle_class_id"]),
            vehicle={
                key: state.payload.get(key)
                for key in (
                    "vehicle_brand_id",
                    "vehicle_brand_name",
                    "vehicle_model_id",
                    "vehicle_model_name",
                    "custom_vehicle_brand",
                    "custom_vehicle_model",
                    "vehicle_year",
                )
            },
            selections=state.payload.get("factor_selections", {}),
            base_price_from=base_from,
            base_price_to=base_to,
            result_price_from=result_from,
            result_price_to=result_to,
        )
        self.session.add(calculation)
        await self.session.flush()
        payload = dict(state.payload)
        payload.update(
            calculation_id=str(calculation.id),
            estimated_price_from=str(result_from),
            estimated_price_to=str(result_to),
        )
        final = await self.states.upsert(
            user_id=user.id,
            flow=PRICE_FLOW,
            step="price_result",
            payload=payload,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        return final, calculation

    async def _state(self, user: User) -> ConversationState:
        state = await self.states.get_active_for_flow(
            user.id, PRICE_FLOW, datetime.now(UTC)
        )
        if state is None or state.step not in {"price_factors", "price_result"}:
            raise VehicleSelectionError("Сценарий расчёта истёк.")
        return state
