"""TAP-1787: ``_load_yaml_config`` must surface YAML parse failures."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import structlog

from tapps_core.config.settings import (
    _load_yaml_config,
    get_last_yaml_load_error,
)


@pytest.fixture(autouse=True)
def _propagate_logs_to_caplog() -> None:
    """structlog needs the stdlib handler attached for caplog to see the records."""
    structlog.configure(
        processors=[structlog.stdlib.add_log_level, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def test_load_yaml_returns_empty_when_missing(tmp_path: Path) -> None:
    # No .tapps-mcp.yaml — silent fall-back to defaults, no error recorded.
    assert _load_yaml_config(tmp_path) == {}
    assert get_last_yaml_load_error() is None


def test_load_yaml_clean_file_records_no_error(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: strict\n", encoding="utf-8")
    data = _load_yaml_config(tmp_path)
    assert data.get("quality_preset") == "strict"
    assert get_last_yaml_load_error() is None


def test_load_yaml_parse_error_logged_at_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad = (
        "quality_preset: strict\n"
        "memory:\n"
        "  safety: enforce\n"
        " : oops_tab_indent_no_key\n"
    )
    (tmp_path / ".tapps-mcp.yaml").write_text(bad, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="tapps_core.config.settings"):
        data = _load_yaml_config(tmp_path)

    assert data == {}, "parse failure must fall back to empty defaults"

    err = get_last_yaml_load_error()
    assert err is not None
    assert ".tapps-mcp.yaml" in err["path"]
    assert err["reason"], "parse reason should be non-empty"

    warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING
        and "mcp_config_yaml_parse_error" in (r.getMessage() or r.message or "")
    ]
    assert warnings, (
        f"expected mcp_config_yaml_parse_error at WARNING; got {[r.message for r in caplog.records]}"
    )


def test_successful_reload_clears_recorded_error(tmp_path: Path) -> None:
    bad = ":\n -invalid\n"
    config = tmp_path / ".tapps-mcp.yaml"
    config.write_text(bad, encoding="utf-8")
    _load_yaml_config(tmp_path)
    assert get_last_yaml_load_error() is not None

    config.write_text("quality_preset: strict\n", encoding="utf-8")
    _load_yaml_config(tmp_path)
    assert get_last_yaml_load_error() is None
