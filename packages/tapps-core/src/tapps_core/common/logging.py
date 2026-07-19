"""Structured logging setup using structlog."""

from __future__ import annotations

import logging
import os
import sys

import structlog


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog for the Tapps platform.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON-formatted logs. Otherwise, use
            colored console output.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def bootstrap_logging_from_env(
    *,
    level_env: str = "TAPPS_MCP_LOG_LEVEL",
    json_env: str = "TAPPS_MCP_LOG_JSON",
) -> tuple[str, bool]:
    """Wire structlog to stderr from env before settings load.

    MCP stdio requires stdout to carry JSON-RPC only. ``load_settings()`` can
    emit structlog lines during validation; without prior ``setup_logging()``,
    structlog's default logger writes to stdout and breaks the MCP handshake.
    """
    level = os.environ.get(level_env, "INFO")
    json_output = os.environ.get(json_env, "").lower() in {"1", "true", "yes"}
    setup_logging(level=level, json_output=json_output)
    return level, json_output


def reconfigure_logging_if_needed(
    settings: object,
    *,
    bootstrap_level: str,
    bootstrap_json: bool,
) -> None:
    """Re-run ``setup_logging`` when resolved settings differ from the bootstrap."""
    level = getattr(settings, "log_level", bootstrap_level)
    json_output = bool(getattr(settings, "log_json", bootstrap_json))
    if level != bootstrap_level or json_output != bootstrap_json:
        setup_logging(level=level, json_output=json_output)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a bound structlog logger.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        A bound structlog logger instance.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
