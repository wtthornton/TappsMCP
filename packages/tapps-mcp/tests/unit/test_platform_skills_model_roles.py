"""Tests for TAP-7386's role-based model routing in platform_skills.py.

Split out of test_platform_skills.py (which was already over the
maintainability gate threshold before this lane) so a fresh, focused
suite doesn't regress that megafile's already-failing score further.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import tapps_mcp.pipeline.platform_skills as platform_skills_module
from tapps_mcp.pipeline.platform_docs_automation import CLAUDE_DOCS_SKILLS, CURSOR_DOCS_SKILLS
from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    MODEL_ROLES,
    RoleResolutionError,
    export_model_roles,
    generate_skills,
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


class TestExportModelRoles:
    """TAP-7795: a machine-readable export derived from MODEL_ROLES at call
    time, so a downstream consumer's routing table can be diffed against
    this repo's actual table instead of a hand-retyped copy."""

    def test_export_contains_all_seven_roles_with_model_and_effort(self) -> None:
        exported = export_model_roles()
        assert set(exported) == EXPECTED_ROLES
        for role, entry in exported.items():
            assert entry["model"] == MODEL_ROLES[role]["model"]
            assert entry["effort"] == MODEL_ROLES[role]["effort"]

    def test_export_is_derived_not_a_second_copy(self, monkeypatch) -> None:
        """Changing the constant changes the export -- proves derivation."""
        monkeypatch.setitem(MODEL_ROLES, "driver", {"model": "claude-opus-5", "effort": "high"})
        assert export_model_roles()["driver"] == {"model": "claude-opus-5", "effort": "high"}

    def test_export_result_does_not_alias_the_module_table(self) -> None:
        """The export returns copies -- mutating the result must not mutate
        MODEL_ROLES itself."""
        exported = export_model_roles()
        exported["driver"]["model"] = "mutated"
        assert MODEL_ROLES["driver"]["model"] != "mutated"

    def test_export_single_role_returns_just_that_entry(self) -> None:
        assert export_model_roles("driver") == {"driver": dict(MODEL_ROLES["driver"])}

    def test_export_unknown_role_refuses_loudly(self) -> None:
        with pytest.raises(RoleResolutionError, match="claude-not-a-model"):
            export_model_roles("claude-not-a-model")

    def test_export_keys_always_match_model_roles_keys(self) -> None:
        """Invariant, not pinned to the current 7 roles: whatever MODEL_ROLES
        contains, export_model_roles must mirror exactly. Guards against the
        export silently becoming a second, independently-maintained copy --
        a role added to MODEL_ROLES without export support would show up
        here as a set mismatch, not as an empty diff."""
        assert set(export_model_roles()) == set(MODEL_ROLES)


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
    effect of moving to role references. TAP-8101 moved the Haiku-pinned
    roles to Sonnet 5, so those rows now expect ``claude-sonnet-5``."""

    EXPECTED_MODELS = {
        "tapps-finish-task": "claude-sonnet-5",
        "tapps-handoff-session": "claude-sonnet-5",
        "tapps-continue-session": "claude-sonnet-5",
        "tapps-review-pipeline": "claude-sonnet-5",
        "tapps-refactor": "claude-sonnet-5",
        "tapps-research": "claude-sonnet-5",
        "tapps-security": "claude-sonnet-5",
        "tapps-memory": "claude-sonnet-5",
        "tapps-tool-reference": "claude-sonnet-5",
        "tapps-init": "claude-sonnet-5",
        "tapps-upgrade": "claude-sonnet-5",
        "tapps-engagement": "claude-sonnet-5",
        "tapps-apply-files": "claude-sonnet-5",
        "linear-issue": "claude-sonnet-5",
        "linear-read": "claude-sonnet-5",
        "linear-release-update": "claude-sonnet-5",
    }

    @pytest.mark.parametrize("skill_name", sorted(EXPECTED_MODELS))
    def test_resolved_model_matches_pre_refactor_assignment(self, skill_name: str) -> None:
        fm = _frontmatter(CLAUDE_SKILLS[skill_name])
        expected_model = self.EXPECTED_MODELS[skill_name]
        assert f"model: {expected_model}" in fm, (
            f"{skill_name} resolved to a different model than before the role-reference refactor"
        )


# ---------------------------------------------------------------------------
# Every generated skill stays model-invocable, on BOTH hosts
# ---------------------------------------------------------------------------
#
# ``disable-model-invocation: true`` removes a skill from the agent's Skill
# tool entirely, yet the generated rules route the agent through these skills
# (``linear-issue`` is the only permitted Linear-write path). TAP-7385 pinned
# every skill but three, which blocked those routes; this reverses it. The
# tests walk the actual dict contents at import time, so a skill added to any
# generated dict later is covered automatically.

_GENERATED_SKILL_DICTS: dict[str, dict[str, str]] = {
    "CLAUDE_SKILLS": CLAUDE_SKILLS,
    "CURSOR_SKILLS": CURSOR_SKILLS,
    "CLAUDE_DOCS_SKILLS": CLAUDE_DOCS_SKILLS,
    "CURSOR_DOCS_SKILLS": CURSOR_DOCS_SKILLS,
}


@pytest.mark.parametrize(
    ("dict_name", "skill_name"),
    [(dict_name, name) for dict_name, skills in _GENERATED_SKILL_DICTS.items() for name in skills],
)
def test_generated_skill_is_model_invocable(dict_name: str, skill_name: str) -> None:
    body = _GENERATED_SKILL_DICTS[dict_name][skill_name]
    assert "disable-model-invocation" not in _frontmatter(body), (
        f"{dict_name}[{skill_name!r}] hides itself from the agent's Skill tool"
    )


def test_linear_routing_skills_are_generated_on_both_hosts() -> None:
    """Known positive for the parametrization above: the skills the generated
    rules make mandatory are actually in the dicts it walks."""
    for name in ("linear-issue", "linear-read", "linear-release-update"):
        assert name in CLAUDE_SKILLS
        assert name in CURSOR_SKILLS


@pytest.mark.parametrize(("platform", "skills_dir"), [("claude", ".claude"), ("cursor", ".cursor")])
def test_generated_skill_files_are_model_invocable(
    tmp_path: Path, platform: str, skills_dir: str
) -> None:
    """Same invariant on the SKILL.md files ``generate_skills`` writes to disk."""
    generate_skills(tmp_path, platform)
    skill_files = sorted((tmp_path / skills_dir / "skills").glob("*/SKILL.md"))
    assert any(f.parent.name == "linear-issue" for f in skill_files)
    pinned = [
        f.parent.name for f in skill_files if "disable-model-invocation" in f.read_text("utf-8")
    ]
    assert pinned == []


@pytest.mark.parametrize(("platform", "skills_dir"), [("claude", ".claude"), ("cursor", ".cursor")])
def test_upgrade_strips_pin_from_existing_consumer_skill(
    tmp_path: Path, platform: str, skills_dir: str
) -> None:
    """A consumer upgraded from a pinned release loses the pin on refresh:
    frontmatter is platform-owned, while the project region below the managed
    block survives."""
    generate_skills(tmp_path, platform)
    target = tmp_path / skills_dir / "skills" / "linear-issue" / "SKILL.md"
    fresh = target.read_text(encoding="utf-8")
    pinned = fresh.replace("\n---\n", "\ndisable-model-invocation: true\n---\n", 1)
    target.write_text(pinned + "\nProject note kept across upgrades.\n", encoding="utf-8")
    assert "disable-model-invocation: true" in _frontmatter(target.read_text(encoding="utf-8"))

    generate_skills(tmp_path, platform, overwrite=True)

    upgraded = target.read_text(encoding="utf-8")
    assert "disable-model-invocation" not in upgraded
    assert "Project note kept across upgrades." in upgraded
