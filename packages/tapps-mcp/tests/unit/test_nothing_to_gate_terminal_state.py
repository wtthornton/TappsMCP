"""TAP-6606 — the "nothing to gate" terminal state.

A session that changed only non-scorable files must be able to finish
honestly: ``tapps_validate_changed`` records that there was nothing to gate,
``tapps_checklist`` completes with that reason instead of demanding a scan of
an untouched file, and the generated stop hook says "nothing needed
validating" rather than "no quality validation was run".

Every positive assertion here is paired with a negative control: the same
fixture with one ``.py`` file changed must still demand the tools and still
block. A test file that only proves the permissive half would be proving a
bypass.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks
from tapps_mcp.tools import nothing_to_gate as ntg
from tapps_mcp.tools.checklist import CallTracker


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A hermetic git repo with one committed ``.md`` and one committed ``.py``."""
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("# base\n", encoding="utf-8")
    (root / "app.py").write_text("X = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _touch_md(root: Path) -> None:
    (root / "README.md").write_text("# base\nchanged prose\n", encoding="utf-8")


def _touch_py(root: Path) -> None:
    (root / "app.py").write_text("X = 2\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# census / marker mechanics
# ---------------------------------------------------------------------------


def test_census_splits_scorable_from_non_scorable(repo: Path) -> None:
    counts = ntg.census(repo, file_paths="docs/a.md, src/b.py, notes.txt")
    assert counts.scorable == ("src/b.py",)
    assert counts.non_scorable == ("docs/a.md", "notes.txt")
    assert counts.changed_files == 3
    assert counts.nothing_to_gate is False


def test_census_from_git_sees_only_the_md_change(repo: Path) -> None:
    _touch_md(repo)
    counts = ntg.census(repo)
    assert counts.non_scorable == ("README.md",)
    assert counts.scorable == ()
    assert counts.nothing_to_gate is True


def test_census_from_git_sees_the_py_change(repo: Path) -> None:
    _touch_py(repo)
    counts = ntg.census(repo)
    assert "app.py" in counts.scorable
    assert counts.nothing_to_gate is False


# ---------------------------------------------------------------------------
# attach_verdict() — TAP-6732: the reason count must track the actual census,
# and nothing_to_gate must reflect it rather than being hard-wired True.
# ---------------------------------------------------------------------------


def test_attach_verdict_reason_count_matches_marker_for_nonexistent_scorable_file(
    repo: Path,
) -> None:
    """A named ``.py`` path that does not exist is still scorable-by-extension.

    The old code hard-coded "0 scorable" in the reason string while the
    sidecar recorded ``scorable_changed: 1`` for the same census — a
    contradiction within one response. Both must agree.
    """
    resp: dict[str, object] = {}
    ntg.attach_verdict(resp, repo, file_paths="ghost.py")

    marker = ntg.read_marker(repo)
    assert marker is not None
    assert marker["scorable_changed"] == 1
    assert "1 scorable" in str(resp["nothing_to_gate_reason"])
    # A scorable (even if unresolvable) file present means this is not the
    # "nothing needed validating" state.
    assert resp["nothing_to_gate"] is False


def test_attach_verdict_reason_count_matches_marker_for_path_validator_rejected_file(
    repo: Path,
) -> None:
    """A traversal path is scorable-by-extension but would be rejected

    downstream by the path validator before any scoring happens. The census
    layer only inspects the extension, so the same contradiction applies.
    """
    resp: dict[str, object] = {}
    ntg.attach_verdict(resp, repo, file_paths="../outside.py")

    marker = ntg.read_marker(repo)
    assert marker is not None
    assert marker["scorable_changed"] == 1
    assert "1 scorable" in str(resp["nothing_to_gate_reason"])
    assert resp["nothing_to_gate"] is False


def test_attach_verdict_nothing_to_gate_true_when_only_non_scorable_changed(
    repo: Path,
) -> None:
    """The unconditional-True case this issue forbids: a purely non-scorable

    changeset must still report ``nothing_to_gate: True``.
    """
    resp: dict[str, object] = {}
    ntg.attach_verdict(resp, repo, file_paths="README.md")

    assert resp["nothing_to_gate"] is True
    assert "0 scorable" in str(resp["nothing_to_gate_reason"])


def test_record_then_read_marker_roundtrip(repo: Path) -> None:
    counts = ntg.census(repo, file_paths="a.md,b.md")
    ntg.record(repo, counts)
    marker = ntg.read_marker(repo)
    assert marker is not None
    assert marker["changed_files"] == 2
    assert marker["scorable_changed"] == 0
    assert marker["non_scorable_changed"] == ["a.md", "b.md"]
    assert "nothing needed validating" in str(marker["reason"])


def test_stale_marker_is_not_readable(repo: Path) -> None:
    ntg.record(repo, ntg.census(repo, file_paths="a.md"))
    path = ntg.marker_path(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["ts"] = time.time() - (ntg.MARKER_MAX_AGE_S + 60)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert ntg.read_marker(repo) is None


def test_clear_drops_the_marker(repo: Path) -> None:
    ntg.record(repo, ntg.census(repo, file_paths="a.md"))
    assert ntg.marker_path(repo).exists()
    ntg.clear(repo)
    assert not ntg.marker_path(repo).exists()
    ntg.clear(repo)  # idempotent


# ---------------------------------------------------------------------------
# resolve() — the read side, with its negative control
# ---------------------------------------------------------------------------


def test_resolve_returns_verdict_when_only_md_changed(repo: Path) -> None:
    _touch_md(repo)
    ntg.record(repo, ntg.census(repo))
    verdict = ntg.resolve(repo)
    assert verdict is not None
    assert "nothing needed validating" in verdict.reason
    assert verdict.non_scorable == ("README.md",)


def test_resolve_refuses_when_a_py_file_changed(repo: Path) -> None:
    """Negative control: a stale marker must not survive a real code change."""
    _touch_md(repo)
    ntg.record(repo, ntg.census(repo))
    _touch_py(repo)
    assert ntg.resolve(repo) is None


def test_resolve_refuses_without_a_recorded_marker(repo: Path) -> None:
    """No marker == validation never ran. Not the same as nothing to gate."""
    _touch_md(repo)
    assert ntg.resolve(repo) is None


def test_resolve_refuses_for_missing_project_root() -> None:
    assert ntg.resolve(None) is None


def test_partition_file_scoped_keeps_non_file_tools_required() -> None:
    still, not_applicable = ntg.partition_file_scoped(
        ["tapps_security_scan", "tapps_release_update", "tapps_score_file"]
    )
    assert still == ["tapps_release_update"]
    assert not_applicable == ["tapps_security_scan", "tapps_score_file"]


# ---------------------------------------------------------------------------
# tapps_checklist
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker(tmp_path: Path):
    CallTracker.reset()
    CallTracker.set_persist_path(tmp_path / "calls.jsonl")
    yield CallTracker
    CallTracker.reset()


def test_checklist_completes_when_nothing_was_gateable(
    repo: Path, tracker: type[CallTracker]
) -> None:
    _touch_md(repo)
    ntg.record(repo, ntg.census(repo))
    tracker.record("tapps_validate_changed")

    result = tracker.evaluate("review", engagement_level="medium", project_root=repo)

    assert result.complete is True
    assert result.missing_required == []
    assert "tapps_security_scan" in result.not_applicable_tools
    assert result.nothing_to_gate is True
    assert "nothing needed validating" in result.nothing_to_gate_reason


def test_checklist_still_blocks_when_a_py_file_changed(
    repo: Path, tracker: type[CallTracker]
) -> None:
    """Negative control: the required tools stay required for real code changes."""
    _touch_md(repo)
    ntg.record(repo, ntg.census(repo))
    _touch_py(repo)
    tracker.record("tapps_validate_changed")

    result = tracker.evaluate("review", engagement_level="medium", project_root=repo)

    assert result.complete is False
    assert "tapps_security_scan" in result.missing_required
    assert result.not_applicable_tools == []
    assert result.nothing_to_gate is False
    assert result.nothing_to_gate_reason == ""


def test_checklist_without_a_marker_still_blocks(repo: Path, tracker: type[CallTracker]) -> None:
    """No recorded verdict == no validation ran. Nothing is demoted."""
    _touch_md(repo)
    tracker.record("tapps_validate_changed")

    result = tracker.evaluate("review", engagement_level="medium", project_root=repo)

    assert result.complete is False
    assert "tapps_security_scan" in result.missing_required
    assert result.nothing_to_gate is False


def test_checklist_keeps_non_file_scoped_tools_required(
    repo: Path, tracker: type[CallTracker]
) -> None:
    """epic requires tapps_checklist, which needs no file — it stays missing."""
    _touch_md(repo)
    ntg.record(repo, ntg.census(repo))

    result = tracker.evaluate("epic", engagement_level="medium", project_root=repo)

    assert result.complete is False
    assert "tapps_checklist" in result.missing_required
    assert result.nothing_to_gate is False


# ---------------------------------------------------------------------------
# validate_changed envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_changed_carries_the_verdict_forward(repo: Path) -> None:
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.validate_changed_output import _handle_no_changed_files

    settings = load_settings().model_copy(update={"project_root": repo})
    resp = await _handle_no_changed_files(
        time.perf_counter_ns(),
        settings,
        lambda *a, **k: None,
        lambda _name, payload: payload,
        explicit_paths=True,
        file_paths="docs/a.md,docs/b.md",
    )
    data = resp["data"]

    assert data["files_validated"] == 0
    assert data["nothing_to_gate"] is True
    assert data["changed_files_seen"] == 2
    assert data["non_scorable_changed"] == ["docs/a.md", "docs/b.md"]
    assert "nothing needed validating" in data["nothing_to_gate_reason"]
    # …and it is persisted, not just returned.
    assert ntg.read_marker(repo) is not None


def test_writing_the_validate_ok_marker_clears_the_verdict(repo: Path) -> None:
    from tapps_mcp.tools.validate_changed_collection import _write_validate_ok_marker

    ntg.record(repo, ntg.census(repo, file_paths="a.md"))
    _write_validate_ok_marker(repo)
    assert not ntg.marker_path(repo).exists()


# ---------------------------------------------------------------------------
# Generated stop hook — executed, not read
# ---------------------------------------------------------------------------


def _run_stop_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    hook = repo / ".claude" / "hooks" / "tapps-stop.sh"
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps({"stop_hook_active": False, "transcript_path": ""}),
        cwd=str(repo),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CLAUDE_PROJECT_DIR": str(repo)},
        capture_output=True,
        text=True,
    )


@pytest.fixture
def hooked_repo(repo: Path) -> Path:
    generate_claude_hooks(repo, force_windows=False, engagement_level="high")
    return repo


def test_generated_stop_hook_reports_nothing_needed_validating(hooked_repo: Path) -> None:
    _touch_md(hooked_repo)
    ntg.record(hooked_repo, ntg.census(hooked_repo))

    proc = _run_stop_hook(hooked_repo)

    assert proc.returncode == 0, proc.stderr
    assert "nothing needed validating" in proc.stderr
    assert "BLOCKED" not in proc.stderr


def test_generated_stop_hook_blocks_when_no_validation_ran(hooked_repo: Path) -> None:
    """Negative control: a changed .py with no validation still exits 2."""
    _touch_py(hooked_repo)

    proc = _run_stop_hook(hooked_repo)

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "BLOCKED: No quality validation was run this session." in proc.stderr
    assert "nothing needed validating" not in proc.stderr


def test_generated_stop_hook_ignores_the_marker_when_py_changed(hooked_repo: Path) -> None:
    """A recorded verdict must never soften the gate for real code changes."""
    ntg.record(hooked_repo, ntg.census(hooked_repo, file_paths="a.md"))
    _touch_py(hooked_repo)

    proc = _run_stop_hook(hooked_repo)

    assert proc.returncode == 2
    assert "BLOCKED: No quality validation was run this session." in proc.stderr


def test_generated_stop_hook_falls_back_to_the_git_wording(hooked_repo: Path) -> None:
    """No marker, no scorable change: honest, but it does not claim validation ran."""
    _touch_md(hooked_repo)

    proc = _run_stop_hook(hooked_repo)

    assert proc.returncode == 0
    assert "OK: no scorable changed files — nothing to validate." in proc.stderr
    assert "nothing needed validating" not in proc.stderr


def test_stop_hook_template_is_the_generator_source() -> None:
    """The two states must be distinguishable strings in the shipped template."""
    from tapps_mcp.pipeline.platform_hook_templates import (
        CLAUDE_HOOK_SCRIPTS_BLOCKING,
        CLAUDE_HOOK_SCRIPTS_BLOCKING_PS,
    )

    for template in (
        CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"],
        CLAUDE_HOOK_SCRIPTS_BLOCKING_PS["tapps-stop.ps1"],
    ):
        assert "nothing needed validating" in template
        assert "BLOCKED: No quality validation was run this session." in template
        assert ".nothing-to-gate.json" in template
