"""Exact-stem smoke tests for tapps_mcp.distribution.doctor_skills (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tapps_mcp.distribution.doctor_skills import (
    check_one_pager_template_current,
    check_orchestration_prompt_learnings_ceiling,
    check_orchestration_prompt_skill_current,
    check_validation_contract_skill_current,
    check_wayfind_skill_current,
)
from tapps_mcp.pipeline.platform_skills import generate_skills
from tapps_mcp.pipeline.platform_templates import ONE_PAGER_REL_PATH, load_one_pager_template
from tapps_mcp.pipeline.skill_managed_block import MARKER_END


def _core_tier_project(tmp_path: Path) -> Path:
    (tmp_path / ".tapps-mcp.yaml").write_text("skill_tier: core\n", encoding="utf-8")
    return tmp_path


def test_check_orchestration_prompt_skill_absent_passes_on_core_tier(tmp_path: Path) -> None:
    result = check_orchestration_prompt_skill_current(_core_tier_project(tmp_path))
    assert result.ok is True
    assert "not required" in result.message


def test_check_wayfind_skill_absent_passes_on_core_tier(tmp_path: Path) -> None:
    result = check_wayfind_skill_current(_core_tier_project(tmp_path))
    assert result.ok is True


def test_check_validation_contract_skill_absent_passes_on_core_tier(tmp_path: Path) -> None:
    result = check_validation_contract_skill_current(_core_tier_project(tmp_path))
    assert result.ok is True


def test_check_orchestration_prompt_skill_missing_fails_on_full_tier(tmp_path: Path) -> None:
    result = check_orchestration_prompt_skill_current(tmp_path)
    assert result.ok is False
    assert "missing" in result.message


def test_truncated_managed_block_fails_even_with_every_old_probed_phrase_present(
    tmp_path: Path,
) -> None:
    """TAP-6948 regression: the old check only probed for markers + companions +
    a handful of substring phrases. A managed block deployed from a stale
    (shorter) emitter still contains every one of those phrases while missing
    everything else — real-world false PASS, measured twice by a peer session
    (a 375-line deployed block against a 616-line current emitter). The
    fingerprint check must FAIL on content, not phrase presence.

    TAP-7017 shrank the managed block itself (progressive disclosure moved the
    bulk of the skill's prose into ``references/``, from ~1,097 lines to under
    400), so the size floor and the probed-phrase list below track the
    post-TAP-7017 SKILL.md rather than the pre-TAP-7017 one — the truncation
    scenario this test exists to catch is unaffected by how large the
    un-truncated block is.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    skill_md = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "SKILL.md"
    full = skill_md.read_text(encoding="utf-8")
    full_lines = full.splitlines(keepends=True)
    assert len(full_lines) > 100, "fixture assumes the real template is well over 100 lines"

    # Derived from content, not a hardcoded line number: as the emitter grows,
    # a literal cut (e.g. line 530) can drift past where a probed phrase now
    # lives, silently breaking the fixture (TAP-6854 round 2 — the emitter
    # grew from 616 to 992+ lines and pushed "expected-fail" from line 527 to
    # 864). Cut just after the LAST probed phrase's line, so every phrase is
    # always retained regardless of emitter length.
    probed_phrases = (
        "validation contract",
        "expected-fail",
        "context lifecycle",
        "host-feature-map",
    )
    lower_lines = [line.lower() for line in full_lines]
    last_phrase_line = max(
        idx for idx, line in enumerate(lower_lines) if any(p in line for p in probed_phrases)
    )
    cut = last_phrase_line + 5  # small margin past the last probed phrase
    assert cut < len(full_lines) * 0.9, (
        "fixture must remain a genuine truncation, not a near-full copy of the emitter"
    )
    truncated_body = "".join(full_lines[:cut]) + MARKER_END + "\n"
    for phrase in probed_phrases:
        assert phrase in truncated_body.lower(), (
            f"fixture must retain {phrase!r} to prove the old blind spot"
        )
    skill_md.write_text(truncated_body, encoding="utf-8")

    result = check_orchestration_prompt_skill_current(tmp_path)
    assert result.ok is False
    assert "stale content" in result.message
    assert "orchestration-prompt" in result.message


def test_check_learnings_ceiling_absent_passes(tmp_path: Path) -> None:
    """No learnings.md deployed at all: nothing to measure, not a failure."""
    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is True
    assert "no learnings.md" in result.message


def test_check_learnings_ceiling_under_ceiling_passes(tmp_path: Path) -> None:
    """TAP-6854 criterion 5 positive control: a small learnings.md must not flag.

    Without this, a check that always fails (or always passes) would look
    identical to a real ceiling check in the over-ceiling test below.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    learnings = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "learnings.md"
    learnings.write_text("- one short lesson (2026-09-02)\n", encoding="utf-8")

    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is True
    assert "under ceiling" in result.message


def test_check_learnings_ceiling_over_bullet_count_fails(tmp_path: Path) -> None:
    """TAP-6854 criterion 5: 'the ceiling is enforced by a check, not by prose'.

    The emitted SKILL.md says 'Past roughly 120 bullets or 40 KB, merge' —
    until this check, nothing ever measured either number. This fixture is
    121 top-level bullets, each far under the byte ceiling on its own, so
    only the bullet-count half of the OR can be responsible for the flag.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    learnings = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "learnings.md"
    bullets = "\n".join(f"- lesson {i} (2026-09-02)" for i in range(121))
    learnings.write_text(bullets + "\n", encoding="utf-8")

    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is False
    assert "past ceiling" in result.message
    assert "orchestration-prompt/learnings.md" in result.message
    assert "breached the bullet ceiling" in result.message


def test_check_learnings_ceiling_over_byte_size_fails(tmp_path: Path) -> None:
    """Same check, other half of the OR: a handful of bullets well over 40 KB."""
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    learnings = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "learnings.md"
    long_bullet = "- " + ("x" * 500) + " (2026-09-02)"
    content = "\n".join(long_bullet for _ in range(100))
    assert len(content.encode("utf-8")) > 40_000, "fixture must clear the byte ceiling"
    learnings.write_text(content + "\n", encoding="utf-8")

    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is False
    assert "past ceiling" in result.message
    assert "breached the byte ceiling" in result.message


def _write_deployed_template(tmp_path: Path, body: str) -> Path:
    deployed_path = tmp_path / ONE_PAGER_REL_PATH
    deployed_path.parent.mkdir(parents=True, exist_ok=True)
    deployed_path.write_text(body, encoding="utf-8")
    return deployed_path


def test_check_one_pager_template_current_when_body_matches_packaged_source(
    tmp_path: Path,
) -> None:
    """TAP-7424 box 1: present + byte-identical to the packaged source passes."""
    _write_deployed_template(tmp_path, load_one_pager_template())

    result = check_one_pager_template_current(tmp_path)
    assert result.ok is True
    assert "current" in result.message

    # Negative control: delete the fixture file on the same tmp_path and
    # re-run — proves the True result above isn't a stub that always
    # returns True regardless of input.
    (tmp_path / ONE_PAGER_REL_PATH).unlink()
    control = check_one_pager_template_current(tmp_path)
    assert control.ok is False


def test_check_one_pager_template_current_fails_when_absent(tmp_path: Path) -> None:
    """TAP-7424 box 2: no docs/templates/ directory at all fails, distinguishably."""
    result = check_one_pager_template_current(tmp_path)
    assert result.ok is False
    assert "missing" in result.message
    assert "stale" not in result.message

    # Negative control: same tmp_path, now correctly deployed, must flip to
    # ok=True — proves the check discriminates rather than always failing.
    _write_deployed_template(tmp_path, load_one_pager_template())
    control = check_one_pager_template_current(tmp_path)
    assert control.ok is True


def test_check_one_pager_template_current_fails_when_body_differs(tmp_path: Path) -> None:
    """TAP-7424 box 3: deployed body differs from the packaged source by one byte."""
    canonical = load_one_pager_template()
    assert canonical, "fixture assumes the packaged template is non-empty"
    mutated = canonical[:-1] + ("Q" if canonical[-1] != "Q" else "R")
    deployed_path = _write_deployed_template(tmp_path, mutated)

    # RED: the mutation is genuinely present and the check fails on it.
    red = check_one_pager_template_current(tmp_path)
    assert red.ok is False
    assert "stale" in red.message
    assert "missing" not in red.message

    # GREEN: restore the exact canonical content on the same path/check call
    # and confirm it now passes — RED then GREEN on one fixture.
    deployed_path.write_text(canonical, encoding="utf-8")
    green = check_one_pager_template_current(tmp_path)
    assert green.ok is True


def test_check_one_pager_template_current_calls_strip_asset_scaffolding(
    tmp_path: Path,
) -> None:
    """TAP-7424 box 5: the comparison calls strip_asset_scaffolding, not raw bytes."""
    _write_deployed_template(tmp_path, load_one_pager_template())

    # Without the patch, the real strip_asset_scaffolding is a no-op on this
    # unmarked content and the fixture is healthy.
    baseline = check_one_pager_template_current(tmp_path)
    assert baseline.ok is True

    # Patched to return a sentinel different from the real deployed content:
    # if the check compared raw file text instead of the function's return
    # value, this patch would have no effect and the result would stay True.
    with patch(
        "tapps_mcp.pipeline.skill_asset_policy.strip_asset_scaffolding",
        return_value="__sentinel_not_the_real_content__",
    ):
        patched = check_one_pager_template_current(tmp_path)
    assert patched.ok is False
    assert "stale" in patched.message
