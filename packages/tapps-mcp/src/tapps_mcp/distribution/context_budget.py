"""Always-on context budget doctor checks (ADR-0031)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.distribution.doctor import CheckResult

_DEFAULT_CONTEXT_BUDGET: dict[str, int] = {
    "claude_md_max_bytes": 12288,
    "agents_md_max_bytes": 24576,
    "always_apply_max_bytes": 16384,
    "skill_count_max": 20,
    "skill_body_max_lines": 120,
    "tier1_warn_bytes": 4096,
    "tier1_fail_bytes": 8192,
    "prose_duplication_warn_bytes": 512,
    "prose_duplication_fail_bytes": 2048,
}

_TIER1_HEADER_RE = re.compile(r"^(#{1,3})\s*Tier[\s-]?1\b", re.IGNORECASE)
_MIN_PROSE_PARAGRAPH_CHARS = 80

_ALWAYS_APPLY_RE = re.compile(
    r"(?im)^alwaysApply\s*:\s*(true|yes|1)\s*$",
)


def _estimate_tokens(byte_count: int) -> int:
    """Rough token estimate used by doctor context-budget messages (chars/4)."""
    return max(0, byte_count // 4)


def read_context_budget(root: Path) -> dict[str, int]:
    """Read ``doctor_context_budget`` from ``.tapps-mcp.yaml`` with defaults."""
    import yaml

    budget = dict(_DEFAULT_CONTEXT_BUDGET)
    config_path = root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return budget
    try:
        with config_path.open(encoding="utf-8") as fh:
            cfg: dict[str, object] = yaml.safe_load(fh) or {}
        raw = cfg.get("doctor_context_budget")
        if not isinstance(raw, dict):
            return budget
        for key in budget:
            value = raw.get(key)
            if isinstance(value, (int, float, str)):
                try:
                    budget[key] = int(value)
                except (TypeError, ValueError):
                    continue
    except Exception:
        return dict(_DEFAULT_CONTEXT_BUDGET)
    return budget


def _file_size_check(
    *,
    check_name: str,
    path: Path,
    max_bytes: int,
    remediation: str,
) -> CheckResult:
    from tapps_mcp.distribution.doctor import CheckResult

    if not path.is_file():
        return CheckResult(check_name, True, f"{path.name} absent — skipping size check")
    size = path.stat().st_size
    tokens = _estimate_tokens(size)
    summary = f"{path.name}: {size} bytes (~{tokens} tokens); ceiling={max_bytes}"
    if size > max_bytes:
        return CheckResult(check_name, False, f"WARN: {summary}", remediation)
    return CheckResult(check_name, True, summary)


def check_claude_md_size(root: Path) -> CheckResult:
    """WARN when ``CLAUDE.md`` exceeds the configured byte ceiling."""
    budget = read_context_budget(root)
    return _file_size_check(
        check_name="CLAUDE.md size",
        path=root / "CLAUDE.md",
        max_bytes=budget["claude_md_max_bytes"],
        remediation=(
            "Trim always-on guidance; move detail into skills or path-scoped rules. "
            "Raise doctor_context_budget.claude_md_max_bytes in .tapps-mcp.yaml to "
            "accept a larger file."
        ),
    )


def check_agents_md_size(root: Path) -> CheckResult:
    """WARN when ``AGENTS.md`` exceeds the configured byte ceiling."""
    budget = read_context_budget(root)
    return _file_size_check(
        check_name="AGENTS.md size",
        path=root / "AGENTS.md",
        max_bytes=budget["agents_md_max_bytes"],
        remediation=(
            "Keep AGENTS.md as essentials + pointer to tapps-tool-reference. "
            "Raise doctor_context_budget.agents_md_max_bytes in .tapps-mcp.yaml to "
            "accept a larger file."
        ),
    )


def _rule_is_always_apply(path: Path) -> bool:
    """True when a rule file's YAML/frontmatter marks ``alwaysApply: true``."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    head = "\n".join(text.splitlines()[:40])
    if not head.lstrip().startswith("---"):
        return False
    end = head.find("\n---", 3)
    frontmatter = head[3:end] if end != -1 else head[3:]
    return _ALWAYS_APPLY_RE.search(frontmatter) is not None


def check_always_apply_rules_weight(root: Path) -> CheckResult:
    """WARN when alwaysApply Claude/Cursor rules exceed the byte ceiling."""
    from tapps_mcp.distribution.doctor import CheckResult

    budget = read_context_budget(root)
    ceiling = budget["always_apply_max_bytes"]
    contributors: list[tuple[str, int]] = []
    for rel_glob in (".claude/rules", ".cursor/rules"):
        base = root / rel_glob
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.suffix not in {".md", ".mdc"}:
                continue
            if not _rule_is_always_apply(path):
                continue
            contributors.append((f"{rel_glob}/{path.name}", path.stat().st_size))

    total = sum(size for _, size in contributors)
    tokens = _estimate_tokens(total)
    detail = ", ".join(f"{name}={size}" for name, size in contributors) or "none"
    summary = (
        f"alwaysApply={total} bytes (~{tokens} tokens) across "
        f"{len(contributors)} file(s); ceiling={ceiling}; {detail}"
    )
    if total > ceiling:
        return CheckResult(
            "alwaysApply rules weight",
            False,
            f"WARN: {summary}",
            "Demote heavy rules to path-scoped / agent-requested, or raise "
            "doctor_context_budget.always_apply_max_bytes in .tapps-mcp.yaml.",
        )
    return CheckResult("alwaysApply rules weight", True, summary)


def _skill_tier(root: Path) -> str:
    """Return ``skill_tier`` from ``.tapps-mcp.yaml`` (default ``full``)."""
    import yaml

    config_path = root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return "full"
    try:
        with config_path.open(encoding="utf-8") as fh:
            cfg: dict[str, object] = yaml.safe_load(fh) or {}
        raw = cfg.get("skill_tier", "full")
        if isinstance(raw, str) and raw.strip().lower() in {"core", "full"}:
            return raw.strip().lower()
    except Exception:
        return "full"
    return "full"


def check_skill_inventory_budget(root: Path) -> CheckResult:
    """WARN on skill count, orphan dirs, and oversized SKILL.md without companions."""
    from tapps_mcp.distribution.doctor import CheckResult, _tapps_skill_bases
    from tapps_mcp.pipeline.platform_docs_automation import (
        CLAUDE_DOCS_SKILLS,
        CURSOR_DOCS_SKILLS,
    )
    from tapps_mcp.pipeline.platform_skills import (
        CLAUDE_SKILLS,
        CURSOR_SKILLS,
        DEPRECATED_TAPPS_SKILLS,
        SKILL_COMPANION_FILES,
    )

    budget = read_context_budget(root)
    count_max = budget["skill_count_max"]
    body_max = budget["skill_body_max_lines"]
    tier = _skill_tier(root)
    registry = (
        set(CLAUDE_SKILLS)
        | set(CURSOR_SKILLS)
        | set(DEPRECATED_TAPPS_SKILLS)
        | set(CLAUDE_DOCS_SKILLS)
        | set(CURSOR_DOCS_SKILLS)
    )

    warns: list[str] = []
    notes: list[str] = []
    host_summaries: list[str] = []
    for host_label, base in _tapps_skill_bases(root):
        if not base.is_dir():
            continue
        skill_dirs = sorted(
            child for child in base.iterdir() if child.is_dir() and (child / "SKILL.md").is_file()
        )
        count = len(skill_dirs)
        host_summaries.append(f"{host_label}={count}")
        if count > count_max:
            warns.append(f"{host_label} has {count} skills (ceiling={count_max})")

        orphans = [d.name for d in skill_dirs if d.name not in registry]
        if orphans:
            preview = ", ".join(orphans[:8])
            more = f" (+{len(orphans) - 8} more)" if len(orphans) > 8 else ""
            # Third-party / AgentForge / user skills are expected extras — never
            # labeled "orphans" (that implies tapps should remove them).
            notes.append(f"{host_label} external skills: {preview}{more}")

        oversized: list[str] = []
        for skill_dir in skill_dirs:
            if skill_dir.name not in registry or skill_dir.name in DEPRECATED_TAPPS_SKILLS:
                continue
            if skill_dir.name in SKILL_COMPANION_FILES:
                continue
            try:
                lines = skill_dir.joinpath("SKILL.md").read_text(encoding="utf-8").count("\n") + 1
            except OSError:
                continue
            if lines > body_max:
                oversized.append(f"{skill_dir.name}({lines})")
        if oversized:
            preview = ", ".join(oversized[:6])
            more = f" (+{len(oversized) - 6} more)" if len(oversized) > 6 else ""
            warns.append(
                f"{host_label} SKILL.md over {body_max} lines without companions: {preview}{more}"
            )

    if not host_summaries:
        return CheckResult(
            "Skill inventory budget",
            True,
            "No deployed skills directories — skipping inventory budget",
        )

    summary = (
        f"hosts: {', '.join(host_summaries)}; ceilings count={count_max} "
        f"lines={body_max}; skill_tier={tier}"
    )
    if notes:
        summary = f"{summary}; {'; '.join(notes)}"
    if warns:
        return CheckResult(
            "Skill inventory budget",
            False,
            f"WARN: {'; '.join(warns)}. {summary}",
            "Split long skills into companions, raise doctor_context_budget.skill_count_max "
            "/ skill_body_max_lines in .tapps-mcp.yaml, or keep skill_tier: full for "
            "AgentForge and other third-party skills (unknown skills are never deleted).",
        )
    return CheckResult("Skill inventory budget", True, summary)


def _tier1_section_bytes(text: str) -> int | None:
    """Return byte size of the first ``Tier 1`` markdown section, else ``None``.

    Looks for a ``# Tier 1`` / ``## Tier-1`` style header (thin-agent
    always-on convention, TAP-5536/TAP-5549) and measures through the next
    header of equal-or-shallower depth, or EOF.
    """
    lines = text.splitlines()
    start_idx: int | None = None
    level = 0
    for i, line in enumerate(lines):
        match = _TIER1_HEADER_RE.match(line.strip())
        if match:
            start_idx = i
            level = len(match.group(1))
            break
    if start_idx is None:
        return None
    close_re = re.compile(r"^#{1," + str(level) + r"}\s")
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if close_re.match(lines[j].strip()):
            end_idx = j
            break
    section = "\n".join(lines[start_idx:end_idx])
    return len(section.encode("utf-8"))


def check_tier1_thin_budget(root: Path) -> CheckResult:
    """WARN/FAIL when a 'Tier 1' section in AGENTS.md/CLAUDE.md exceeds thin-agent ceilings.

    Opt-in: skips silently when neither file tags a Tier-1 section, so
    consumers who do not use this convention see no noise. Pure text/byte
    measurement — no ontology or knowledge-graph lookup involved (TAP-5549).
    """
    from tapps_mcp.distribution.doctor import CheckResult

    budget = read_context_budget(root)
    warn_ceiling = budget["tier1_warn_bytes"]
    fail_ceiling = budget["tier1_fail_bytes"]

    found: list[tuple[str, int]] = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        size = _tier1_section_bytes(text)
        if size is not None:
            found.append((name, size))

    if not found:
        return CheckResult(
            "Tier-1 thin budget",
            True,
            "No 'Tier 1' section marker found in AGENTS.md/CLAUDE.md — skipping",
        )

    detail = ", ".join(f"{name}={size}B" for name, size in found)
    worst = max(size for _, size in found)
    summary = (
        f"{detail}; ceilings warn={warn_ceiling}B fail={fail_ceiling}B "
        f"(~{_estimate_tokens(worst)} tokens worst)"
    )
    if worst > fail_ceiling:
        return CheckResult(
            "Tier-1 thin budget",
            False,
            summary,
            "Tier-1 section exceeds the hard ceiling — move detail into skills / "
            "progressive disclosure. Raise doctor_context_budget.tier1_fail_bytes "
            "in .tapps-mcp.yaml only if this is intentional.",
        )
    if worst > warn_ceiling:
        return CheckResult(
            "Tier-1 thin budget",
            False,
            f"WARN: {summary}",
            "Trim the Tier-1 section toward the thin-agent budget, or raise "
            "doctor_context_budget.tier1_warn_bytes in .tapps-mcp.yaml.",
        )
    return CheckResult("Tier-1 thin budget", True, summary)


def _prose_paragraphs(text: str) -> set[str]:
    """Split into whitespace-normalized paragraphs, filtering short blocks."""
    blocks = re.split(r"\n\s*\n", text)
    return {
        normalized
        for block in blocks
        if len(normalized := " ".join(block.split())) >= _MIN_PROSE_PARAGRAPH_CHARS
    }


def check_prose_duplication(root: Path) -> CheckResult:
    """WARN/FAIL when AGENTS.md and CLAUDE.md repeat the same prose blocks verbatim.

    Generalizes ``check_karpathy_dual_install`` (one known duplicate) into a
    byte-budget signal for any paragraph granted into both always-on files —
    the classic thin-agent bloat pattern. Pure text comparison; no ontology
    or knowledge-graph lookup involved (TAP-5549).
    """
    from tapps_mcp.distribution.doctor import CheckResult

    budget = read_context_budget(root)
    warn_ceiling = budget["prose_duplication_warn_bytes"]
    fail_ceiling = budget["prose_duplication_fail_bytes"]

    texts: dict[str, str] = {}
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if path.is_file():
            try:
                texts[name] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

    if len(texts) < 2:
        return CheckResult(
            "Prose duplication",
            True,
            "AGENTS.md and CLAUDE.md not both present — skipping duplication check",
        )

    duplicates = _prose_paragraphs(texts["AGENTS.md"]) & _prose_paragraphs(texts["CLAUDE.md"])
    if not duplicates:
        return CheckResult(
            "Prose duplication",
            True,
            "No duplicated prose blocks between AGENTS.md and CLAUDE.md",
        )

    total_bytes = sum(len(block.encode("utf-8")) for block in duplicates)
    preview = next(iter(duplicates))[:80]
    summary = (
        f"{len(duplicates)} duplicated block(s), {total_bytes}B; "
        f'ceilings warn={warn_ceiling}B fail={fail_ceiling}B; e.g. "{preview}..."'
    )
    if total_bytes > fail_ceiling:
        return CheckResult(
            "Prose duplication",
            False,
            summary,
            "Duplicated prose exceeds the hard ceiling — keep a single home for "
            "this guidance (AGENTS.md when managed, else CLAUDE.md) and link "
            "instead of copying. Raise doctor_context_budget.prose_duplication_fail_bytes "
            "in .tapps-mcp.yaml only if this is intentional.",
        )
    if total_bytes > warn_ceiling:
        return CheckResult(
            "Prose duplication",
            False,
            f"WARN: {summary}",
            "Consolidate duplicated guidance into one file, or raise "
            "doctor_context_budget.prose_duplication_warn_bytes in .tapps-mcp.yaml.",
        )
    return CheckResult("Prose duplication", True, summary)


def check_karpathy_dual_install(root: Path) -> CheckResult:
    """WARN when Karpathy guidelines are installed in both CLAUDE.md and AGENTS.md."""
    from tapps_mcp.distribution.doctor import CheckResult
    from tapps_mcp.pipeline import karpathy_block

    homes = [name for name in ("CLAUDE.md", "AGENTS.md") if karpathy_block.has_block(root / name)]
    if len(homes) >= 2:
        return CheckResult(
            "Karpathy dual install",
            False,
            f"WARN: Karpathy guidelines present in both {', '.join(homes)}",
            "Keep a single home (AGENTS.md when managed, else CLAUDE.md). "
            "Run tapps-mcp upgrade --force to strip the secondary copy, or add "
            "'karpathy' to upgrade_skip_files to leave as-is.",
        )
    if homes:
        return CheckResult("Karpathy dual install", True, f"Single home: {homes[0]}")
    return CheckResult(
        "Karpathy dual install",
        True,
        "Karpathy block not installed in CLAUDE.md or AGENTS.md",
    )
