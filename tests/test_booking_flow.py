from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.booking import normalize_vehicle_name, render_summary, services_done
from app.models import Service, ServiceCategory


def test_vehicle_names_are_normalized_and_limited() -> None:
    assert normalize_vehicle_name("  Mercedes   Benz  ", 80) == "Mercedes Benz"
    assert normalize_vehicle_name("   ", 80) is None
    assert normalize_vehicle_name("x" * 81, 80) is None


@pytest.mark.asyncio
async def test_service_selection_must_not_be_empty() -> None:
    callback = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(get_data=AsyncMock(return_value={}))

    await services_done(callback, state, SimpleNamespace())  # type: ignore[arg-type]

    callback.answer.assert_awaited_once_with("Выберите хотя бы одну услугу", show_alert=True)


@pytest.mark.asyncio
async def test_summary_contains_vehicle_and_services(session: AsyncSession) -> None:
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
    await session.commit()
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "brand": "BMW",
                "model": "X5",
                "year": 2022,
                "vehicle_class": "кроссовер",
                "service_ids": [str(service.id)],
            }
        ),
        set_state=AsyncMock(),
    )
    callback = SimpleNamespace(message=SimpleNamespace(edit_text=AsyncMock()), answer=AsyncMock())

    await render_summary(callback, state, session)  # type: ignore[arg-type]

    state.set_state.assert_awaited_once()
    text = callback.message.edit_text.await_args.args[0]
    assert "BMW" in text and "X5" in text and "Wash" in text
