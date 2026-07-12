"""Safe process-wide logging configuration."""

from __future__ import annotations

import logging
import logging.config


class ContextDefaultsFilter(logging.Filter):
    """Provide optional structured fields expected by the formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        for field_name in ("signal", "bot_id", "bot_username", "timezone"):
            if not hasattr(record, field_name):
                setattr(record, field_name, "-")
        return True


def configure_logging(level: str) -> None:
    """Configure readable UTC-independent console logs without secrets."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"context_defaults": {"()": ContextDefaultsFilter}},
            "formatters": {
                "default": {
                    "format": (
                        "%(asctime)s | %(levelname)s | %(name)s | %(message)s "
                        "| signal=%(signal)s bot_id=%(bot_id)s "
                        "bot_username=%(bot_username)s timezone=%(timezone)s"
                    )
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["context_defaults"],
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": level, "handlers": ["console"]},
            "loggers": {
                "sqlalchemy.engine": {"level": "WARNING"},
                "aiogram.event": {"level": "WARNING"},
            },
        }
    )
