"""Tests for tapps_core.common.logging — structured logging setup."""

from __future__ import annotations

import logging

import structlog

from tapps_core.common.logging import get_logger, setup_logging


class TestSetupLogging:
    """Verify setup_logging configures the root logger correctly."""

    def test_sets_log_level(self) -> None:
        setup_logging(level="WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_default_level_is_info(self) -> None:
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_json_output_does_not_raise(self) -> None:
        # Smoke test: JSON renderer is wired without errors
        setup_logging(level="DEBUG", json_output=True)

    def test_handler_is_attached(self) -> None:
        setup_logging()
        root = logging.getLogger()
        assert len(root.handlers) >= 1

    def test_quiets_noisy_loggers(self) -> None:
        setup_logging()
        assert logging.getLogger("httpx").level >= logging.WARNING
        assert logging.getLogger("httpcore").level >= logging.WARNING


class TestGetLogger:
    """Verify get_logger returns a usable structlog BoundLogger."""

    def test_returns_bound_logger(self) -> None:
        log = get_logger("test_module")
        assert log is not None
        # BoundLogger should have standard log methods
        assert callable(getattr(log, "info", None))
        assert callable(getattr(log, "warning", None))
