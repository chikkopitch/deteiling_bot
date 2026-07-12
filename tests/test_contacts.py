import pytest

from app.services.contacts import normalize_person_name, normalize_russian_phone
from app.services.vehicle_selection import VehicleSelectionError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8 999 123-45-67", "+79991234567"),
        ("7 (999) 123 45 67", "+79991234567"),
        ("+7-999-123-45-67", "+79991234567"),
    ],
)
def test_normalize_russian_phone(raw: str, expected: str) -> None:
    assert normalize_russian_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "+69991234567", "+799912345678"])
def test_invalid_phone_is_rejected(raw: str) -> None:
    with pytest.raises(VehicleSelectionError):
        normalize_russian_phone(raw)


def test_person_name_is_trimmed_and_control_characters_removed() -> None:
    assert normalize_person_name("  Иван\n  Иванов  ") == "Иван Иванов"


def test_empty_name_is_rejected() -> None:
    with pytest.raises(VehicleSelectionError):
        normalize_person_name("   ")
