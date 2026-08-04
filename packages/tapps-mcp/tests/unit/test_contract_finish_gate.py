"""Tests for contract / creator-verifier checklist hard-gate (TAP-5543/5548)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker, ChecklistResult
from tapps_mcp.tools.contract_telemetry import (
    record_contract_verified,
    record_creator_verifier,
)

_EVALUATE_TARGET = "tapps_mcp.tools.checklist.CallTracker.evaluate"
_SETTINGS_TARGET = "tapps_mcp.server.load_settings"


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    CallTracker.reset()


def _complete_result() -> ChecklistResult:
    return ChecklistResult(
        task_type="feature",
        called=["tapps_session_start", "tapps_validate_changed", "tapps_checklist"],
        missing_required=[],
        missing_recommended=[],
        missing_optional=[],
        missing_required_hints=[],
        missing_recommended_hints=[],
        missing_optional_hints=[],
        complete=True,
        total_calls=3,
    )


def _write_py_edit(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    mod = src / "feat.py"
    mod.write_text("x = 1\n", encoding="utf-8")
    metrics = tmp_path / ".tapps-mcp"
    metrics.mkdir(parents=True)
    (metrics / "loop-metrics.jsonl").write_text(
        json.dumps(
            {
                "ts": int(time.time()),
                "files_edited": [str(mod.relative_to(tmp_path))],
                "gate_skipped_files": [],
                "lookup_docs_called": True,
                "checklist_called": True,
                "tools_used": ["tapps_validate_changed", "tapps_checklist"],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _settings(tmp_path: Path) -> MagicMock:
    mock = MagicMock()
    mock.quality_preset = "standard"
    mock.project_root = tmp_path
    mock.checklist_require_success = False
    mock.checklist_strict_unknown_task_types = False
    return mock


@pytest.mark.asyncio
async def test_feature_checklist_blocks_without_marks(tmp_path: Path) -> None:
    _write_py_edit(tmp_path)
    with (
        patch(_EVALUATE_TARGET, return_value=_complete_result()),
        patch(_SETTINGS_TARGET, return_value=_settings(tmp_path)),
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=False)

    data: dict[str, Any] = resp.get("data", resp)
    assert data["complete"] is False
    missing = data.get("missing_required") or []
    assert "contract_assertions_unverified" in missing
    assert "creator_verifier_skipped" in missing
    gaps = (data.get("usage_gaps") or {}).get("gaps") or []
    assert "contract_assertions_unverified" in gaps
    assert "creator_verifier_skipped" in gaps


@pytest.mark.asyncio
async def test_feature_checklist_complete_after_marks(tmp_path: Path) -> None:
    _write_py_edit(tmp_path)
    record_contract_verified(tmp_path)
    record_creator_verifier(tmp_path)
    with (
        patch(_EVALUATE_TARGET, return_value=_complete_result()),
        patch(_SETTINGS_TARGET, return_value=_settings(tmp_path)),
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="feature", auto_run=False)

    data: dict[str, Any] = resp.get("data", resp)
    assert data["complete"] is True
    gaps = (data.get("usage_gaps") or {}).get("gaps") or []
    assert "contract_assertions_unverified" not in gaps
    assert "creator_verifier_skipped" not in gaps


@pytest.mark.asyncio
async def test_bugfix_does_not_hard_block_on_contract_gaps(tmp_path: Path) -> None:
    """Hard gate is feature/review only; bugfix may still surface usage_gaps."""
    _write_py_edit(tmp_path)
    result = _complete_result()
    result.task_type = "bugfix"
    with (
        patch(_EVALUATE_TARGET, return_value=result),
        patch(_SETTINGS_TARGET, return_value=_settings(tmp_path)),
    ):
        from tapps_mcp.server import tapps_checklist

        resp = await tapps_checklist(task_type="bugfix", auto_run=False)

    data: dict[str, Any] = resp.get("data", resp)
    assert data["complete"] is True
    gaps = (data.get("usage_gaps") or {}).get("gaps") or []
    assert "contract_assertions_unverified" in gaps
