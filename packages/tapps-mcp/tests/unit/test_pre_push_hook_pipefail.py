"""Smoke tests for the pre-push hook pipefail fix (TAP-1784).

Without ``set -o pipefail`` the gating command ``pytest ... | tail -20`` masks
pytest's exit code with tail's, so the hook never blocks on red. These tests
prove (a) the hook source now sets pipefail and (b) the kernel pipe semantics
behave as the fix assumes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parents[4] / ".githooks" / "pre-push"


@pytest.fixture(scope="module")
def hook_source() -> str:
    assert HOOK_PATH.exists(), f"pre-push hook missing at {HOOK_PATH}"
    return HOOK_PATH.read_text(encoding="utf-8")


def test_hook_sets_pipefail(hook_source: str) -> None:
    """TAP-1784: pipefail must be enabled for the pytest pipeline to gate."""
    assert "set -o pipefail" in hook_source


def test_hook_references_story(hook_source: str) -> None:
    """The pipefail line should be commented with the story id for traceability."""
    assert "TAP-1784" in hook_source


def test_hook_pipes_pytest_through_tail(hook_source: str) -> None:
    """If this pattern changes, the pipefail fix may no longer be necessary."""
    assert "pytest" in hook_source
    assert "| tail" in hook_source


def test_pipefail_propagates_pytest_failure_through_tail() -> None:
    """With pipefail, a failing left-hand side returns non-zero through tail."""
    result = subprocess.run(
        ["bash", "-c", "set -e; set -o pipefail; false | tail -20"],
        capture_output=True,
    )
    assert result.returncode != 0


def test_without_pipefail_failure_is_masked_by_tail() -> None:
    """Document the bug pattern: without pipefail, the pipeline exits 0."""
    result = subprocess.run(
        ["bash", "-c", "set -e; false | tail -20"],
        capture_output=True,
    )
    assert result.returncode == 0
