"""TAP-7016: recurring_validation_skips must not fire for a no-source repo.

Kept in its own file rather than appended to the (already oversized)
``test_usage_gaps_hint.py`` -- that file's maintainability score is already
flagged, and every line added there degrades it further for no benefit.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from tapps_mcp.tools.usage import compute_gaps


def _init_git_repo(tmp_path: Path, *, tracked_files: list[str]) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    for rel in tracked_files:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)


def _write_high_skip_loops(tmp_path: Path) -> None:
    metrics_dir = tmp_path / ".tapps-mcp"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    rows = [
        {
            "ts": now - i,
            "files_edited": ["src/a.py"],
            "gate_skipped_files": ["src/a.py"],
            "lookup_docs_called": False,
            "checklist_called": False,
            "tools_used": [],
        }
        for i in range(4)
    ]
    (metrics_dir / "loop-metrics.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_no_source_repo_suppresses_recommendation(tmp_path: Path) -> None:
    """Acceptance: zero scorable files in the repo -> no blocking-escalation rec."""
    _init_git_repo(tmp_path, tracked_files=["README.md", "scripts/deploy.sh"])
    _write_high_skip_loops(tmp_path)

    report = compute_gaps(tmp_path, called_tools={"tapps_session_start"})

    assert "recurring_validation_skips" not in report["gaps"]
    assert report["source_profile"] == "no_source"
    assert not any("raising engagement to high" in rec for rec in report["recommendations"])


def test_has_source_repo_still_recommends(tmp_path: Path) -> None:
    """Acceptance: real scorable source + genuinely high skip rate still fires."""
    _init_git_repo(tmp_path, tracked_files=["README.md", "packages/tapps_mcp/module.py"])
    _write_high_skip_loops(tmp_path)

    report = compute_gaps(tmp_path, called_tools={"tapps_session_start"})

    assert "recurring_validation_skips" in report["gaps"]
    assert report["source_profile"] == "has_source"
    assert any("raising engagement to high" in rec for rec in report["recommendations"])


def test_unknown_profile_refuses_to_suppress(tmp_path: Path) -> None:
    """Guardrail: when git can't answer (not a repo here), never silently drop the gap."""
    _write_high_skip_loops(tmp_path)

    report = compute_gaps(tmp_path, called_tools={"tapps_session_start"})

    assert report["source_profile"] == "unknown"
    assert "recurring_validation_skips" in report["gaps"]
