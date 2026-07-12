import pytest

from app.utils.phone import mask_phone, normalize_phone


@pytest.mark.parametrize("raw", ["8 912 345-67-89", "+7(912)3456789", "79123456789"])
def test_normalize_russian_phone(raw: str) -> None:
    assert normalize_phone(raw) == "+79123456789"


def test_invalid_phone() -> None:
    with pytest.raises(ValueError):
        normalize_phone("123")


def test_mask_phone() -> None:
    assert mask_phone("+79123456789") == "+7***6789"
