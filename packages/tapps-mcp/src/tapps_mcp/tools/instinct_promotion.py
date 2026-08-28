"""Staged instinct -> served brain memory promotion (KB-3.8, Ruling 8, TAP-6701).

Selects homunculus instincts (``~/.claude/homunculus/projects/<id>/instincts/``)
that have earned enough confidence and repeated observation to graduate from
personal, per-session heuristics into a project-scoped brain memory entry.
Promotion always requires an explicit human operator accept (SC-6) — this
module only ever produces a diff (``select_instinct_candidates`` +
``render_dry_run_report``); ``apply_promotions`` performs the write and is the
caller's responsibility to gate behind that accept.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

# "Observed 24+ times in session ...", "Observed 10 instances of 3+
# consecutive Read operations...", "Observed 12 writes...", "Observed 331
# Read calls..." — the wording after the count varies across projects (fleet
# recon, TAP-6701: 21/267 confidence>=0.85 instincts across this machine's
# homunculus tree use a noun other than times/instances), so match on the
# "Observed <N>" prefix alone rather than an enumerated word list. The
# leading integer is the count that feeds the >=3-observations selector
# criterion — real files carry exactly one such line, never repeated dated
# bullets, so "observations" means this count, not the bullet count.
_OBSERVED_RE = re.compile(r"Observed\s+(\d+)\+?\b", re.IGNORECASE)
_LAST_OBSERVED_RE = re.compile(r"Last observed:\s*(\S+)")
_ACTION_RE = re.compile(r"^##\s*Action\s*$\n(.*?)(?:\n##\s|\Z)", re.DOTALL | re.MULTILINE)

DEFAULT_MIN_CONFIDENCE = 0.85
DEFAULT_MIN_OBSERVATIONS = 3
# Instincts are behavioral heuristics with no natural MemoryTier of their own;
# "pattern" is the closest existing tier (matches `memory save`'s own default).
_PROMOTED_TIER = "pattern"


def _resolve_homunculus_project_id(
    homunculus_root: Path,
    project_root: Path,
    project_name: str | None,
) -> str | None:
    """Resolve the homunculus project hash for *project_root* (or *project_name*).

    ``projects.json`` maps ``<hash>`` -> ``{id, name, root, ...}``. Matching by
    ``root`` (this checkout's absolute path) is the unambiguous default;
    ``--project <name>`` lets an operator target a different project's
    instincts explicitly.
    """
    projects_file = homunculus_root / "projects.json"
    if not projects_file.is_file():
        return None
    try:
        data = json.loads(projects_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if project_name:
        for project_id, meta in data.items():
            if isinstance(meta, dict) and meta.get("name") == project_name:
                return str(project_id)
        return None
    resolved_root = str(project_root.resolve())
    for project_id, meta in data.items():
        if isinstance(meta, dict) and meta.get("root") == resolved_root:
            return str(project_id)
    return None


def _parse_instinct_file(
    path: Path,
    *,
    min_confidence: float,
    min_observations: int,
) -> dict[str, Any] | None:
    """Return a candidate dict for *path*, or None if it does not qualify."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    frontmatter_raw, body = parts[1], parts[2]
    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict):
        return None
    if "promoted_key" in frontmatter:
        # Idempotency: a previously-applied instinct is never a candidate
        # again, so a second `--apply` run makes 0 additional promote calls.
        return None

    confidence = frontmatter.get("confidence")
    if not isinstance(confidence, int | float) or confidence < min_confidence:
        return None

    observed_counts = [int(m.group(1)) for m in _OBSERVED_RE.finditer(body)]
    if not observed_counts or max(observed_counts) < min_observations:
        return None
    if not _LAST_OBSERVED_RE.search(body):
        return None

    action_match = _ACTION_RE.search(body)
    action_text = action_match.group(1).strip() if action_match else ""
    instinct_id = str(frontmatter.get("id") or path.stem)

    return {
        "id": instinct_id,
        "file": path,
        "proposed_key": instinct_id,
        "value": action_text,
        "tier": _PROMOTED_TIER,
        "scope": str(frontmatter.get("scope") or "project"),
        "evidence": f"instinct:{instinct_id}",
        "confidence": float(confidence),
        "observed_count": max(observed_counts),
    }


def select_instinct_candidates(
    homunculus_root: Path,
    project_root: Path,
    *,
    project_name: str | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> list[dict[str, Any]]:
    """Scan this project's homunculus instincts for promotion candidates.

    Returns an empty list (never raises) when ``projects.json`` is missing,
    the project has no recorded homunculus entry, or it has no instincts dir
    — promotion is opt-in enrichment, not a required capability.
    """
    project_id = _resolve_homunculus_project_id(homunculus_root, project_root, project_name)
    if project_id is None:
        return []
    candidates: list[dict[str, Any]] = []
    for subdir in ("personal", "inherited"):
        instincts_dir = homunculus_root / "projects" / project_id / "instincts" / subdir
        if not instincts_dir.is_dir():
            continue
        for md_file in sorted(instincts_dir.glob("*.md")):
            candidate = _parse_instinct_file(
                md_file, min_confidence=min_confidence, min_observations=min_observations
            )
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def render_dry_run_report(candidates: list[dict[str, Any]]) -> str:
    """Render a human-readable diff of promotion candidates."""
    if not candidates:
        return (
            "No instinct promotion candidates "
            f"(confidence >= {DEFAULT_MIN_CONFIDENCE}, "
            f">= {DEFAULT_MIN_OBSERVATIONS} observations, not already promoted).\n"
        )
    lines = [f"{len(candidates)} instinct promotion candidate(s):", ""]
    for candidate in candidates:
        lines.append(f"+ key: {candidate['proposed_key']}")
        lines.append(
            f"  tier: {candidate['tier']}  scope: {candidate['scope']}  "
            f"confidence: {candidate['confidence']:.2f}  "
            f"observed: {candidate['observed_count']}"
        )
        lines.append(f"  evidence: {candidate['evidence']}")
        value_preview = candidate["value"].replace("\n", " ")[:200]
        lines.append(f"  value: {value_preview}")
        lines.append("")
    return "\n".join(lines)


def _append_promoted_key(path: Path, key: str) -> None:
    """Append ``promoted_key: <key>`` to *path*'s frontmatter in place."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter_raw = parts[1]
    new_frontmatter = frontmatter_raw.rstrip("\n") + f"\npromoted_key: {key}\n"
    new_text = "---" + new_frontmatter + "---" + parts[2]
    path.write_text(new_text, encoding="utf-8")


DEFAULT_REPORT_PATH = Path("reports") / "promote-instincts.md"


def write_dry_run_report(candidates: list[dict[str, Any]], report_path: Path | None) -> Path:
    """Render and write the dry-run diff, returning the path written to."""
    report = render_dry_run_report(candidates)
    out_path = report_path or DEFAULT_REPORT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return out_path


async def apply_promotions(
    candidates: list[dict[str, Any]],
    bridge: Any,
    *,
    operator: str,
) -> list[dict[str, Any]]:
    """Promote each candidate via ``bridge.promote_instinct`` (Ruling 8).

    Skips any candidate whose file has since gained ``promoted_key:`` (belt
    and suspenders — ``select_instinct_candidates`` already excludes these,
    so a second call over the same candidate list is a no-op). Never called
    against the live brain or the real ``~/.claude/homunculus/`` tree from
    this lane (SC-6) — only against ``tmp_path`` fixtures with a mocked
    ``bridge``.
    """
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        current = candidate["file"].read_text(encoding="utf-8")
        frontmatter_raw = current.split("---", 2)[1] if current.startswith("---") else ""
        if "promoted_key:" in frontmatter_raw:
            continue
        result = await bridge.promote_instinct(
            key=candidate["proposed_key"],
            value=candidate["value"],
            tier=candidate["tier"],
            scope=candidate["scope"],
            signal="human",
            actor=f"operator:{operator}",
            evidence=candidate["evidence"],
        )
        _append_promoted_key(candidate["file"], candidate["proposed_key"])
        results.append({"id": candidate["id"], "key": candidate["proposed_key"], "result": result})
    return results
