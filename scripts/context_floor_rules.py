"""Always-loaded rule and CLAUDE.md measurement for the context-efficiency epic (SG0).

A deployed ``.claude/rules/*.md`` file is always-loaded when its frontmatter
has no ``paths:`` glob scoping to defer it -- see ``measure_rules`` for the
exact contract, including today's ``alwaysApply: false`` nuance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from context_floor_core import _CLAUDE_MD, _RULES_DIR, MeasurementError


@dataclass
class RuleInfo:
    name: str
    byte_count: int
    always_loaded: bool
    frontmatter_keys: list[str]
    always_apply_false: bool


def _parse_rule_frontmatter(text: str) -> dict[str, str] | None:
    """Return {key: first-line value} for a rule file's frontmatter block,
    or None if the file has no ``---``-delimited frontmatter at all (e.g.
    repo-workflow.md) -- absence of frontmatter is itself meaningful: with
    no ``paths:`` scoping declared, the file is always-loaded by default.
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    end: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if line and line[0] not in " \t-" and ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def measure_rules(rules_dir: Path = _RULES_DIR) -> tuple[int, list[RuleInfo]]:
    """A rule is always-loaded when its frontmatter has no ``paths:`` glob
    scoping -- this includes files with no frontmatter block at all, and
    (per today's actual, observed session behavior) files that declare
    ``alwaysApply: false`` without also declaring ``paths:``: that flag is
    recorded in ``detail`` for a later sub-goal but does not by itself defer
    loading today.
    """
    if not rules_dir.is_dir():
        raise MeasurementError(f"rules directory not found: {rules_dir}")

    infos: list[RuleInfo] = []
    total = 0
    for path in sorted(rules_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        byte_count = len(text.encode("utf-8"))
        frontmatter = _parse_rule_frontmatter(text)
        always_loaded = frontmatter is None or "paths" not in frontmatter
        always_apply_false = (
            frontmatter is not None
            and frontmatter.get("alwaysApply", "").strip().lower() == "false"
        )
        infos.append(
            RuleInfo(
                name=path.name,
                byte_count=byte_count,
                always_loaded=always_loaded,
                frontmatter_keys=sorted(frontmatter) if frontmatter else [],
                always_apply_false=always_apply_false,
            )
        )
        if always_loaded:
            total += byte_count
    return total, infos


def measure_claude_md(path: Path = _CLAUDE_MD) -> int:
    if not path.is_file():
        raise MeasurementError(f"CLAUDE.md not found: {path}")
    return len(path.read_bytes())
