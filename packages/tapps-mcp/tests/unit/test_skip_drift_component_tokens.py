"""TAP-7430: component-name skip tokens must not false-warn as missing/drifting.

``karpathy`` and ``docs_automation`` are entries in :data:`SKIP_TOKENS` whose
value is the component's own name, not a filesystem path (see
``tapps_core.config.upgrade_skip_tokens`` module docstring). A bare
``(project_root / rel_path).exists()`` check on those always fails, so
``check_upgrade_skip_token_drift`` reported a perfectly valid token as
"points at a path that no longer exists" -- a false positive. A genuinely
missing FILE-path token (e.g. an unrendered ``.claude/rules/*.md``) must
still be reported as missing.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_core.config.upgrade_skip_tokens import ALL_SKIP_TOKENS, SKIP_TOKENS
from tapps_mcp.distribution.doctor_skip_drift import check_upgrade_skip_token_drift


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def test_vocabulary_population_is_a_mix_of_component_and_path_tokens() -> None:
    """Vacuity check: name what is counted and assert it is non-zero."""
    component_tokens = {
        key for key, paths in SKIP_TOKENS.items() if paths == frozenset({key})
    }
    path_tokens = set(SKIP_TOKENS) - component_tokens

    assert len(ALL_SKIP_TOKENS) == 31
    assert component_tokens == {"karpathy", "docs_automation"}
    assert len(path_tokens) == 29


def test_component_name_token_does_not_report_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEGATIVE control: at base (unfixed) this assertion fails -- 'karpathy'
    appears in the missing-report because the check does a bare path-exists
    test against a component name that is not a filesystem path."""
    monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["karpathy"]))

    check = check_upgrade_skip_token_drift(tmp_path)

    assert check.ok
    assert "no longer exists" not in check.message
    assert "not yet drift-checkable" in check.message
    assert "karpathy" in check.message


def test_docs_automation_component_token_does_not_report_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["docs_automation"]))

    check = check_upgrade_skip_token_drift(tmp_path)

    assert check.ok
    assert "no longer exists" not in check.message
    assert "not yet drift-checkable" in check.message


def test_genuinely_missing_file_path_token_still_reported_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POSITIVE control: a real file-path token that does not exist on disk
    must still be reported as missing -- the fix must not silence every
    missing-path report, only the component-name false positive."""
    monkeypatch.setenv(
        "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/rules/autonomy.md"])
    )

    check = check_upgrade_skip_token_drift(tmp_path)

    assert check.severity == "warn"
    assert "no longer exists" in check.message
    assert ".claude/rules/autonomy.md" in check.message
