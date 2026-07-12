"""Expire currently overdue temporary slot reservations once."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_database_settings  # noqa: E402
from app.database.session import create_database  # noqa: E402
from app.scheduler.reservations import expire_reservations_once  # noqa: E402


async def cleanup() -> int:
    database = create_database(get_database_settings())
    try:
        async with database.session_factory() as session:
            async with session.begin():
                return await expire_reservations_once(session)
    finally:
        await database.dispose()


def run() -> None:
    try:
        expired = asyncio.run(cleanup())
    except Exception as error:
        print(
            f"Reservation cleanup failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    print(f"Expired reservations processed: {expired}.")


if __name__ == "__main__":
    run()
