"""Global asyncio exception reporting."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def install_asyncio_exception_handler() -> None:
    """Log unhandled background task failures through application logging."""
    loop = asyncio.get_running_loop()

    def handle_exception(
        event_loop: asyncio.AbstractEventLoop,
        context: dict[str, object],
    ) -> None:
        exception = context.get("exception")
        message = str(context.get("message", "Unhandled asyncio exception"))
        if isinstance(exception, BaseException):
            logger.error(
                message,
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ),
            )
        else:
            logger.error("%s; context=%r", message, context)

    loop.set_exception_handler(handle_exception)
