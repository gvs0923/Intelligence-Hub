import logging
import sys

import structlog

from src.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    # Configure Python's standard logging to just pass everything through;
    # structlog will do the actual formatting.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,   # pull in request-scoped context
        structlog.processors.add_log_level,         # adds "level": "info"
        structlog.processors.TimeStamper(fmt="iso"),  # adds ISO timestamp
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,       # nicely format exceptions
    ]

    if settings.environment == "development":
        # Pretty, colored, human-readable output for local dev
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Compact JSON for production (machine-parseable)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)