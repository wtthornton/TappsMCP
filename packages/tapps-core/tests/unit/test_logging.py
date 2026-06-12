"""Tests for tapps_core.common.logging — structured logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tapps_core.common.logging import (
    bootstrap_logging_from_env,
    get_logger,
    reconfigure_logging_if_needed,
    setup_logging,
)


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


class TestBootstrapLoggingFromEnv:
    """MCP stdio bootstrap must configure stderr before settings load."""

    def test_bootstrap_defaults_to_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPPS_MCP_LOG_LEVEL", raising=False)
        monkeypatch.delenv("TAPPS_MCP_LOG_JSON", raising=False)
        level, json_output = bootstrap_logging_from_env()
        assert level == "INFO"
        assert json_output is False
        assert logging.getLogger().level == logging.INFO

    def test_bootstrap_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_MCP_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("TAPPS_MCP_LOG_JSON", "true")
        level, json_output = bootstrap_logging_from_env()
        assert level == "WARNING"
        assert json_output is True


class TestReconfigureLoggingIfNeeded:
    def test_skips_when_unchanged(self) -> None:
        setup_logging(level="INFO", json_output=False)

        class _Settings:
            log_level = "INFO"
            log_json = False

        reconfigure_logging_if_needed(
            _Settings(),
            bootstrap_level="INFO",
            bootstrap_json=False,
        )
        assert logging.getLogger().level == logging.INFO

    def test_reconfigures_when_yaml_overrides(self) -> None:
        bootstrap_logging_from_env()

        class _Settings:
            log_level = "ERROR"
            log_json = True

        reconfigure_logging_if_needed(
            _Settings(),
            bootstrap_level="INFO",
            bootstrap_json=False,
        )
        assert logging.getLogger().level == logging.ERROR

    def test_load_settings_after_bootstrap_stays_off_stdout(
        self,
        capfd: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Memory project-id auto-derive must not print to stdout on MCP stdio."""
        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID", "brain-only-proj")
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        bootstrap_logging_from_env()
        from tapps_core.config.settings import load_settings

        load_settings(project_root=tmp_path)
        captured = capfd.readouterr()
        assert captured.out == ""


class TestGetLogger:
    """Verify get_logger returns a usable structlog BoundLogger."""

    def test_returns_bound_logger(self) -> None:
        log = get_logger("test_module")
        assert log is not None
        # BoundLogger should have standard log methods
        assert callable(getattr(log, "info", None))
        assert callable(getattr(log, "warning", None))
