"""Create or promote the configured Telegram account to owner."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_database_settings  # noqa: E402
from app.database.enums import AdminRole  # noqa: E402
from app.database.models import Admin  # noqa: E402
from app.database.session import create_database  # noqa: E402


def parse_telegram_id(value: str) -> int:
    """Parse a positive numeric Telegram ID without accepting booleans/floats."""
    try:
        telegram_id = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Telegram ID must be an integer") from error
    if telegram_id <= 0:
        raise argparse.ArgumentTypeError("Telegram ID must be positive")
    return telegram_id


async def create_owner(telegram_id: int) -> str:
    database = create_database(get_database_settings())
    try:
        async with database.session_factory() as session:
            async with session.begin():
                admin = await session.scalar(
                    select(Admin)
                    .where(Admin.telegram_id == telegram_id)
                    .with_for_update()
                )
                if admin is None:
                    session.add(
                        Admin(
                            telegram_id=telegram_id,
                            role=AdminRole.OWNER,
                            is_active=True,
                        )
                    )
                    return "created"
                changed = admin.role != AdminRole.OWNER or not admin.is_active
                admin.role = AdminRole.OWNER
                admin.is_active = True
                return "updated" if changed else "already exists"
    finally:
        await database.dispose()


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "telegram_id",
        nargs="?",
        type=parse_telegram_id,
        help="numeric Telegram ID; defaults to OWNER_TELEGRAM_ID",
    )
    args = parser.parse_args()
    raw_id = args.telegram_id
    if raw_id is None:
        env_value = get_database_settings().owner_telegram_id
        if env_value is None:
            parser.error("provide Telegram ID or set OWNER_TELEGRAM_ID")
        raw_id = env_value
    try:
        result = asyncio.run(create_owner(raw_id))
    except Exception as error:
        print(
            f"Owner creation failed: {type(error).__name__}: {error}", file=sys.stderr
        )
        raise SystemExit(1) from error
    print(f"Owner {raw_id}: {result}.")


if __name__ == "__main__":
    run()
