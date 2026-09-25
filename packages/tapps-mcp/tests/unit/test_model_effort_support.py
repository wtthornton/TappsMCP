"""TAP-8101: no generated skill or agent pins Claude Haiku 4.5, and no
generated frontmatter pairs ``effort:`` with a model that lacks effort support.

Haiku 4.5 does not accept the effort parameter (it uses extended-thinking
``budget_tokens``) and its retirement is "not sooner than 2026-10-15"
(platform.claude.com/docs/en/about-claude/models/overview, checked
2026-09-24). Every ``MODEL_ROLES`` entry carries an effort, so every role must
name an effort-capable model.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import tapps_mcp.pipeline.platform_docs_automation as docs_automation_module
from tapps_mcp.pipeline.platform_docs_automation import (
    CLAUDE_DOC_AGENTS,
    CLAUDE_DOCS_SKILLS,
    CURSOR_DOC_AGENTS,
    CURSOR_DOCS_SKILLS,
)
from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    MODEL_ROLES,
    generate_skills,
)
from tapps_mcp.pipeline.platform_subagents import (
    CLAUDE_AGENTS,
    CURSOR_AGENTS,
    generate_subagent_definitions,
)

HAIKU_4_5 = "claude-haiku-4-5"

# Models whose effort support is documented on the Claude Code model-config
# page ("Models not listed here do not support effort"), plus the aliases
# that resolve to one of them. ``haiku`` is deliberately absent.
EFFORT_CAPABLE_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "fable",
        "opus",
        "sonnet",
    }
)

GENERATED_BODIES: dict[str, dict[str, str]] = {
    "CLAUDE_SKILLS": CLAUDE_SKILLS,
    "CURSOR_SKILLS": CURSOR_SKILLS,
    "CLAUDE_DOCS_SKILLS": CLAUDE_DOCS_SKILLS,
    "CURSOR_DOCS_SKILLS": CURSOR_DOCS_SKILLS,
    "CLAUDE_AGENTS": CLAUDE_AGENTS,
    "CURSOR_AGENTS": CURSOR_AGENTS,
    "CLAUDE_DOC_AGENTS": CLAUDE_DOC_AGENTS,
    "CURSOR_DOC_AGENTS": CURSOR_DOC_AGENTS,
}

_MODEL_LINE_RE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)
_EFFORT_LINE_RE = re.compile(r"^effort:\s*(\S+)\s*$", re.MULTILINE)


def _frontmatter(body: str) -> str:
    return body.split("---", 2)[1]


def _effort_without_support(body: str) -> str | None:
    """Return a reason when *body*'s frontmatter pairs effort with a model
    that does not support it, else ``None``."""
    fm = _frontmatter(body)
    effort = _EFFORT_LINE_RE.search(fm)
    if effort is None:
        return None
    model = _MODEL_LINE_RE.search(fm)
    if model is None:
        return f"effort: {effort.group(1)} with no model: line to check support against"
    if model.group(1) not in EFFORT_CAPABLE_MODELS:
        return f"effort: {effort.group(1)} paired with model: {model.group(1)}"
    return None


_ALL_BODIES = [
    (dict_name, name) for dict_name, bodies in GENERATED_BODIES.items() for name in bodies
]


@pytest.mark.parametrize(("dict_name", "name"), _ALL_BODIES)
def test_generated_body_does_not_pin_haiku_4_5(dict_name: str, name: str) -> None:
    assert HAIKU_4_5 not in GENERATED_BODIES[dict_name][name]


@pytest.mark.parametrize(("dict_name", "name"), _ALL_BODIES)
def test_generated_frontmatter_never_pairs_effort_with_unsupported_model(
    dict_name: str, name: str
) -> None:
    reason = _effort_without_support(GENERATED_BODIES[dict_name][name])
    assert reason is None, f"{dict_name}[{name!r}]: {reason}"


@pytest.mark.parametrize(("platform", "root"), [("claude", ".claude"), ("cursor", ".cursor")])
def test_generated_files_on_disk_carry_no_haiku_4_5(
    tmp_path: Path, platform: str, root: str
) -> None:
    generate_skills(tmp_path, platform)
    generate_subagent_definitions(tmp_path, platform)
    files = sorted((tmp_path / root).rglob("*.md"))
    assert any(f.parent.name == "linear-issue" for f in files)
    assert [str(f) for f in files if HAIKU_4_5 in f.read_text("utf-8")] == []


class TestEffortSupportCheckDiscriminates:
    """Known positive and negative for the frontmatter check above, which
    otherwise passes vacuously while no generated body carries ``effort:``."""

    def test_flags_effort_paired_with_haiku(self) -> None:
        body = "---\nname: x\nmodel: claude-haiku-4-5-20251001\neffort: low\n---\nbody\n"
        assert _effort_without_support(body) is not None

    def test_flags_effort_paired_with_haiku_alias(self) -> None:
        assert _effort_without_support("---\nmodel: haiku\neffort: low\n---\n") is not None

    def test_flags_effort_without_a_model_line(self) -> None:
        assert _effort_without_support("---\nname: x\neffort: low\n---\n") is not None

    def test_accepts_effort_paired_with_sonnet_5(self) -> None:
        assert _effort_without_support("---\nmodel: claude-sonnet-5\neffort: low\n---\n") is None

    def test_accepts_model_without_effort(self) -> None:
        body = "---\nmodel: claude-haiku-4-5-20251001\n---\n"
        assert _effort_without_support(body) is None


@pytest.mark.parametrize("role", sorted(MODEL_ROLES))
def test_every_role_pairs_its_effort_with_an_effort_capable_model(role: str) -> None:
    entry = MODEL_ROLES[role]
    assert entry["effort"], f"role {role!r} has no effort"
    assert entry["model"] in EFFORT_CAPABLE_MODELS, (
        f"role {role!r} pairs effort {entry['effort']!r} with {entry['model']!r}"
    )


def test_docs_automation_source_has_no_literal_model_id() -> None:
    """``platform_docs_automation.py`` resolves models through MODEL_ROLES."""
    source = inspect.getsource(docs_automation_module)
    assert "model: claude-" not in source
    assert "model: {{model:" in source
