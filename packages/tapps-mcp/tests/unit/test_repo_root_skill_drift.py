"""Repo-root drift guard for the checked-in orchestration-prompt skill (TAP-6693).

PR #372 (472d0374, TAP-7078/6968/6857) changed the managed-block emitter
(preserved regions + emitter-derived block hash) without anyone regenerating
the checked-in ``.claude/skills/orchestration-prompt`` /
``.cursor/skills/orchestration-prompt`` copies, so
``check_orchestration_prompt_skill_current`` silently drifted with nothing to
catch it: every existing caller (``test_doctor_skills.py``,
``test_orchestration_prompt_skill.py``) runs the check against a synthetic
``tmp_path`` / consumer root freshly built by ``generate_skills``, never
against the repo's own checked-in tree.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tapps_mcp.distribution.context_budget import _skill_tier
from tapps_mcp.distribution.doctor_skills import check_orchestration_prompt_skill_current
from tapps_mcp.pipeline.skill_managed_block import MARKER_BEGIN_PREFIX, MARKER_END


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "packages").is_dir() and (parent / ".claude").is_dir():
            return parent
    raise RuntimeError("could not locate repo root above test_repo_root_skill_drift.py")


REPO_ROOT = _find_repo_root()


def test_orchestration_prompt_skill_current_at_repo_root() -> None:
    """The checked-in copies must match what the current emitter would produce.

    Asserts the message names both hosts, not just ``ok is True`` — a
    ``skill_tier: core`` project reports ``ok=True`` with a "not required"
    message that would let this test pass for the wrong reason.
    """
    tier = _skill_tier(REPO_ROOT)
    assert tier == "full", (
        f"repo-root .tapps-mcp.yaml resolved skill_tier={tier!r}, expected 'full' — "
        "a 'core' tier would make this check vacuously pass without inspecting content"
    )

    result = check_orchestration_prompt_skill_current(REPO_ROOT)

    assert result.ok is True, result.message
    assert "claude" in result.message
    assert "cursor" in result.message


def _seed_from_repo_root(tmp_path: Path) -> None:
    """Copy the checked-in orchestration-prompt skill (both hosts) into *tmp_path*.

    Mutates only the copy under *tmp_path*; REPO_ROOT is never written to.
    Also copies ``.tapps-mcp.yaml`` since ``_skill_tier`` reads it from the
    project root being checked.
    """
    for host_dir in (".claude", ".cursor"):
        src = REPO_ROOT / host_dir / "skills" / "orchestration-prompt"
        dest = tmp_path / host_dir / "skills" / "orchestration-prompt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
    shutil.copy(REPO_ROOT / ".tapps-mcp.yaml", tmp_path / ".tapps-mcp.yaml")


def test_repo_root_drift_is_detected_missing_marker(tmp_path: Path) -> None:
    """Negative control 1: strip the managed-block marker from the claude copy only.

    Proves the guard test actually discriminates: without this control, a
    check that always returns ``ok=True`` would look identical to the real
    pass above.
    """
    _seed_from_repo_root(tmp_path)
    claude_skill_md = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "SKILL.md"
    content = claude_skill_md.read_text(encoding="utf-8")
    assert MARKER_END in content, "fixture assumes the repo-root copy carries a managed block"
    claude_skill_md.write_text(content.replace(MARKER_END, ""), encoding="utf-8")

    result = check_orchestration_prompt_skill_current(tmp_path)

    assert result.ok is False
    assert "claude/orchestration-prompt stale (no managed-block marker)" in result.message
    assert "cursor/orchestration-prompt stale" not in result.message


def test_repo_root_drift_is_detected_stale_content(tmp_path: Path) -> None:
    """Negative control 2: mutate one line inside the managed block of the cursor copy.

    Markers stay intact here (unlike the missing-marker control above), so
    this exercises the content-fingerprint comparison specifically — the
    exact drift TAP-6693 describes (PR #372 changed the emitter; the
    checked-in block still parses fine, it just no longer matches).
    """
    _seed_from_repo_root(tmp_path)
    cursor_skill_md = tmp_path / ".cursor" / "skills" / "orchestration-prompt" / "SKILL.md"
    content = cursor_skill_md.read_text(encoding="utf-8")
    begin_idx = content.index(MARKER_BEGIN_PREFIX)
    end_idx = content.index(MARKER_END)
    assert begin_idx < end_idx, "fixture assumes BEGIN precedes END"
    head, block_body, tail = content[:begin_idx], content[begin_idx:end_idx], content[end_idx:]
    lines = block_body.splitlines(keepends=True)
    # Line 0 is the BEGIN marker itself (version-normalized by the check, so
    # mutating it wouldn't prove content drift) — pick the first prose line
    # after it, inside the managed block.
    target_idx = next(
        i
        for i, line in enumerate(lines)
        if i > 0 and line.strip() and not line.lstrip().startswith("<!--")
    )
    lines[target_idx] = f"MUTATED-BY-TEST {lines[target_idx]}"
    mutated = head + "".join(lines) + tail
    assert mutated != content
    cursor_skill_md.write_text(mutated, encoding="utf-8")

    result = check_orchestration_prompt_skill_current(tmp_path)

    assert result.ok is False
    assert "cursor/orchestration-prompt stale content" in result.message
    assert "claude/orchestration-prompt stale" not in result.message
