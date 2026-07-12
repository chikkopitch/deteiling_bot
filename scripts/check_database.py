"""Standalone PostgreSQL connectivity check."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_database_settings  # noqa: E402
from app.database.session import create_database  # noqa: E402


async def check_database() -> None:
    settings = get_database_settings()
    database = create_database(settings)
    try:
        await database.check_connection()
    finally:
        await database.dispose()


def run() -> None:
    try:
        asyncio.run(check_database())
    except Exception as error:
        print(
            f"PostgreSQL connection failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    print("PostgreSQL connection is available (SELECT 1 succeeded).")


if __name__ == "__main__":
    run()
