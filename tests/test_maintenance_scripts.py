from __future__ import annotations

import argparse

import pytest

from scripts.create_owner import parse_telegram_id
from scripts.seed_initial_data import CONTENT, SERVICES, VEHICLE_CLASSES


def test_create_owner_telegram_id_validation() -> None:
    assert parse_telegram_id("123456789") == 123456789
    with pytest.raises(argparse.ArgumentTypeError):
        parse_telegram_id("0")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_telegram_id("not-a-number")


def test_initial_seed_contains_required_defaults_without_duplicate_keys() -> None:
    assert len(VEHICLE_CLASSES) >= 1
    assert any(service[4] for service in SERVICES)
    assert "welcome_text" in CONTENT
    assert len({item[0] for item in VEHICLE_CLASSES}) == len(VEHICLE_CLASSES)
    assert len({item[0] for item in SERVICES}) == len(SERVICES)
