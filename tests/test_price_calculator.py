from decimal import Decimal
from types import SimpleNamespace

from app.services.price_calculator import calculate_range


def value(coefficient: str = "1", surcharge: str = "0"):
    return SimpleNamespace(
        coefficient=Decimal(coefficient), fixed_surcharge=Decimal(surcharge)
    )


def test_calculator_applies_database_coefficients_with_decimal() -> None:
    result = calculate_range(
        Decimal("1000.00"),
        Decimal("1500.00"),
        [value("1.20"), value("1.10")],
    )
    assert result == (Decimal("1320.00"), Decimal("1980.00"))


def test_calculator_adds_fixed_surcharges_after_coefficients() -> None:
    result = calculate_range(
        Decimal("1000.00"),
        Decimal("1200.00"),
        [value("1.25", "300.00"), value("1", "200.00")],
    )
    assert result == (Decimal("1750.00"), Decimal("2000.00"))


def test_calculator_preserves_range_without_factors() -> None:
    assert calculate_range(Decimal("999.99"), Decimal("1499.99"), []) == (
        Decimal("999.99"),
        Decimal("1499.99"),
    )
