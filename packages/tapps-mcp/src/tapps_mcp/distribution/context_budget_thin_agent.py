"""Thin-agent doctor checks: Tier-1 section budget + prose duplication (TAP-5549).

Kept out of ``context_budget.py`` on purpose: that facade scores below the
quality gate even untouched (TAP-5540), so any edit there would drag the
whole megafile into the PR diff and fail CI. This sibling module owns the
checks outright and is wired directly from ``doctor_runner`` instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.distribution.doctor import CheckResult

_TIER1_HEADER_RE = re.compile(r"^(#{1,3})\s*Tier[\s-]?1\b", re.IGNORECASE)
_MIN_PROSE_PARAGRAPH_CHARS = 80

_DEFAULT_THIN_AGENT_BUDGET: dict[str, int] = {
    "tier1_warn_bytes": 4096,
    "tier1_fail_bytes": 8192,
    "prose_duplication_warn_bytes": 512,
    "prose_duplication_fail_bytes": 2048,
}


def _estimate_tokens(byte_count: int) -> int:
    """Rough token estimate used by doctor context-budget messages (chars/4)."""
    return max(0, byte_count // 4)


def _read_thin_agent_budget(root: Path) -> dict[str, int]:
    """Read the four thin-agent ``doctor_context_budget`` keys from ``.tapps-mcp.yaml``."""
    import yaml

    budget = dict(_DEFAULT_THIN_AGENT_BUDGET)
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
        return dict(_DEFAULT_THIN_AGENT_BUDGET)
    return budget


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

    budget = _read_thin_agent_budget(root)
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

    budget = _read_thin_agent_budget(root)
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
