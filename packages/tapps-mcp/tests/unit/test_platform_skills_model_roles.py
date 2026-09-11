"""Tests for TAP-7386's role-based model routing in platform_skills.py.

Split out of test_platform_skills.py (which was already over the
maintainability gate threshold before this lane) so a fresh, focused
suite doesn't regress that megafile's already-failing score further.
"""

from __future__ import annotations

import inspect

import pytest

import tapps_mcp.pipeline.platform_skills as platform_skills_module
from tapps_mcp.pipeline.platform_skills import (
    AMBIENT_FRONT_DOOR_SKILL_NAMES,
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    MODEL_ROLES,
    RoleResolutionError,
    resolve_role_model,
)

EXPECTED_ROLES = frozenset(
    {
        "driver",
        "lane",
        "verifier-deterministic",
        "verifier-comparative",
        "verifier-semantic",
        "explorer",
        "prose",
    }
)


def _frontmatter(template: str) -> str:
    return template.split("---", 2)[1]


class TestModelRolesTable:
    """A single derived table maps a role name to a model + effort, so a
    model migration is a one-place edit in ``MODEL_ROLES`` instead of one
    edit per skill template."""

    def test_role_vocabulary_matches_tap_7386(self) -> None:
        assert set(MODEL_ROLES) == EXPECTED_ROLES

    @pytest.mark.parametrize("role", sorted(EXPECTED_ROLES))
    def test_each_role_names_a_model_and_an_effort(self, role: str) -> None:
        entry = MODEL_ROLES[role]
        assert entry.get("model"), f"role {role!r} has no model"
        assert entry.get("effort"), f"role {role!r} has no effort"

    def test_resolve_role_model_returns_the_table_value(self) -> None:
        for role, entry in MODEL_ROLES.items():
            assert resolve_role_model(role) == entry["model"]


class TestModelRoleNegativeControls:
    """TAP-7386 acceptance: unknown refuses, unknown never passes."""

    def test_resolve_role_model_rejects_unknown_role(self) -> None:
        with pytest.raises(RoleResolutionError, match="claude-not-a-model"):
            resolve_role_model("claude-not-a-model")

    def test_resolve_role_model_rejects_corrupt_table_entry(self, monkeypatch) -> None:
        monkeypatch.setitem(MODEL_ROLES, "driver", None)
        with pytest.raises((RoleResolutionError, TypeError)):
            resolve_role_model("driver")


class TestNoLiteralModelIdsInTemplates:
    def test_base_dict_has_no_hardcoded_model_literal(self) -> None:
        source = inspect.getsource(platform_skills_module)
        base_dict_source = source.split("CLAUDE_SKILLS.update(CLAUDE_DOMAIN_SKILLS)")[0]
        assert "model: claude-" not in base_dict_source


class TestResolvedModelsUnchanged:
    """TAP-7386 acceptance: no skill's effective model changes as a side
    effect of moving to role references."""

    EXPECTED_MODELS = {
        "tapps-finish-task": "claude-haiku-4-5-20251001",
        "tapps-handoff-session": "claude-haiku-4-5-20251001",
        "tapps-continue-session": "claude-haiku-4-5-20251001",
        "tapps-review-pipeline": "claude-sonnet-5",
        "tapps-refactor": "claude-sonnet-5",
        "tapps-research": "claude-sonnet-5",
        "tapps-security": "claude-sonnet-5",
        "tapps-memory": "claude-sonnet-5",
        "tapps-tool-reference": "claude-haiku-4-5-20251001",
        "tapps-init": "claude-sonnet-5",
        "tapps-upgrade": "claude-sonnet-5",
        "tapps-engagement": "claude-haiku-4-5-20251001",
        "tapps-apply-files": "claude-haiku-4-5-20251001",
        "linear-issue": "claude-haiku-4-5-20251001",
        "linear-read": "claude-haiku-4-5-20251001",
        "linear-release-update": "claude-haiku-4-5-20251001",
    }

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_MODELS))
    def test_resolved_model_matches_pre_refactor_assignment(self, skill_name: str) -> None:
        fm = _frontmatter(CLAUDE_SKILLS[skill_name])
        expected_model = self.EXPECTED_MODELS[skill_name]
        assert f"model: {expected_model}" in fm, (
            f"{skill_name} resolved to a different model than before the "
            "role-reference refactor"
        )


# ---------------------------------------------------------------------------
# TAP-7385: ambient-invocation coverage across BOTH host dicts
# ---------------------------------------------------------------------------
#
# PR #392 pinned disable-model-invocation on CLAUDE_SKILLS only: 220 tests
# passed while CURSOR_SKILLS was never touched, because every assertion
# parametrized over a hand-typed CLAUDE_SKILLS-only list. These tests walk
# the actual dict contents at import time instead, so a name added to either
# dict later is covered automatically. Housed here (not in
# test_platform_skills.py) because that file is already below the
# maintainability gate threshold and this parametrization would regress its
# ratchet baseline further.


def _ambient_violations(skills: dict[str, str], exempt: frozenset[str]) -> list[str]:
    """Names in ``skills`` that violate the ambient invariant: an exempt name
    that carries the pin, or a non-exempt name that lacks it."""
    violations = []
    for name, body in skills.items():
        fm = _frontmatter(body)
        pinned = "disable-model-invocation: true" in fm
        should_be_ambient = name in exempt
        if should_be_ambient and pinned:
            violations.append(f"{name} (exempt but pinned)")
        elif not should_be_ambient and not pinned:
            violations.append(f"{name} (not exempt but ambient)")
    return violations


class TestClaudeAmbientCoverage:
    """A1/A2: every CLAUDE_SKILLS entry outside the 3 front doors is pinned."""

    @pytest.mark.parametrize(
        "skill_name",
        sorted(set(CLAUDE_SKILLS) - AMBIENT_FRONT_DOOR_SKILL_NAMES),
    )
    def test_non_front_door_carries_pin(self, skill_name: str) -> None:
        fm = _frontmatter(CLAUDE_SKILLS[skill_name])
        assert "disable-model-invocation: true" in fm, (
            f"{skill_name} is ambient but is not one of the stated front doors "
            f"({sorted(AMBIENT_FRONT_DOOR_SKILL_NAMES)})"
        )

    @pytest.mark.parametrize("skill_name", sorted(AMBIENT_FRONT_DOOR_SKILL_NAMES))
    def test_front_door_stays_ambient(self, skill_name: str) -> None:
        fm = _frontmatter(CLAUDE_SKILLS[skill_name])
        assert "disable-model-invocation:" not in fm


class TestCursorAmbientCoverage:
    """A1: CURSOR_SKILLS carries the same pin on every non-front-door entry.

    This class is the actual fix for the gap described in the lane brief --
    before it existed, nothing in this test suite ever imported CURSOR_SKILLS
    into a disable-model-invocation assertion."""

    @pytest.mark.parametrize(
        "skill_name",
        sorted(set(CURSOR_SKILLS) - AMBIENT_FRONT_DOOR_SKILL_NAMES),
    )
    def test_non_front_door_carries_pin(self, skill_name: str) -> None:
        fm = _frontmatter(CURSOR_SKILLS[skill_name])
        assert "disable-model-invocation: true" in fm, (
            f"{skill_name} is ambient but is not one of the stated front doors "
            f"({sorted(AMBIENT_FRONT_DOOR_SKILL_NAMES)})"
        )

    @pytest.mark.parametrize("skill_name", sorted(AMBIENT_FRONT_DOOR_SKILL_NAMES))
    def test_front_door_stays_ambient(self, skill_name: str) -> None:
        fm = _frontmatter(CURSOR_SKILLS[skill_name])
        assert "disable-model-invocation:" not in fm


class TestFrontDoorAllowlistIsNameSensitive:
    """A3: the check must fail on a same-size name swap, not just a count
    change -- otherwise an allowlist that silently drifts to the wrong names
    would still read as green."""

    def test_swapping_a_front_door_name_breaks_the_invariant(self) -> None:
        swapped = (AMBIENT_FRONT_DOOR_SKILL_NAMES - {"tapps-wayfind"}) | {"tapps-security"}
        assert len(swapped) == len(AMBIENT_FRONT_DOOR_SKILL_NAMES)

        claude_violations = _ambient_violations(CLAUDE_SKILLS, swapped)
        cursor_violations = _ambient_violations(CURSOR_SKILLS, swapped)

        # tapps-wayfind is real-ambient but no longer in the swapped allowlist
        # -> flagged as "not exempt but ambient". tapps-security is real-pinned
        # but now (wrongly) in the allowlist -> flagged as "exempt but pinned".
        assert any("tapps-wayfind" in v for v in claude_violations)
        assert any("tapps-security" in v for v in claude_violations)
        assert any("tapps-wayfind" in v for v in cursor_violations)
        assert any("tapps-security" in v for v in cursor_violations)
