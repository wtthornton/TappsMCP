"""Doctor gate-mode detection + managed-skill freshness checks (TAP-5606 split).

Covers the Linear cache-gate / session-start-gate mode+violation helpers,
the ``_tapps_skill_bases`` skill-host resolver (imported by
:mod:`tapps_mcp.distribution.doctor_skills` and several sibling ``doctor_*``
modules), and the skill-deployment checks that depend on it
(``tapps-finish-task``, ``tapps-memory``, session-handoff skills, deprecated
wrapper skills).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tapps_mcp.distribution.doctor_result import CheckResult

#: Violation log the Stop hook appends to in warn mode (TAP-6586).
COMPLETION_GATE_VIOLATIONS_LOG = ".completion-gate-violations.jsonl"


def _detect_cache_gate_mode(project_root: Path) -> str:
    """Read the baked MODE from the installed pre-list hook script (TAP-1224).

    Returns "warn" or "block" when the script is present and parseable; "off"
    otherwise. Reads the first 20 lines so the file does not have to be loaded
    in full for a doctor sweep.
    """
    script = project_root / ".claude" / "hooks" / "tapps-pre-linear-list.sh"
    if not script.exists():
        return "off"
    try:
        with script.open(encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(20))
    except OSError:
        return "off"
    if 'MODE="block"' in head:
        return "block"
    if 'MODE="warn"' in head:
        return "warn"
    return "off"


def _detect_completion_gate_mode(project_root: Path) -> str:
    """Read the completion-gate mode baked into the installed stop hook (TAP-6586).

    Sibling of :func:`_detect_cache_gate_mode`. The stop hook has no ``MODE=``
    line to read — the two variants differ in what they do — so the mode is
    inferred from the behaviour that is actually deployed: the blocking hook
    exits 2 on missing validation, the warn hook only appends to the violation
    log. Returns "off" when neither marker is present.
    """
    script = project_root / ".claude" / "hooks" / "tapps-stop.sh"
    if not script.exists():
        return "off"
    try:
        body = script.read_text(encoding="utf-8")
    except OSError:
        return "off"
    if "BLOCKED:" in body:
        return "block"
    if COMPLETION_GATE_VIOLATIONS_LOG in body:
        return "warn"
    return "off"


def _count_completion_gate_violations_24h(project_root: Path) -> int:
    """Count completion-gate violations from the last 24 h (TAP-6586).

    Sibling of :func:`_count_cache_gate_violations_24h`. Reads
    ``.tapps-mcp/.completion-gate-violations.jsonl`` and counts entries whose
    ``ts`` is within 24 hours of now. The stop hook writes ``ts`` as an integer
    Unix epoch (the cache-gate hook writes an ISO string), so this parses
    epochs; unparseable lines are skipped. Returns 0 when the log is missing —
    a doctor-time signal, not a gate, so failures degrade silently.
    """
    log_path = project_root / ".tapps-mcp" / COMPLETION_GATE_VIOLATIONS_LOG
    if not log_path.exists():
        return 0
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).timestamp()
    count = 0
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                try:
                    ts = float(entry["ts"])
                except (KeyError, TypeError, ValueError):
                    continue
                if ts >= cutoff:
                    count += 1
    except OSError:
        return count
    return count


def _detect_session_start_gate_mode(project_root: Path) -> str:
    """Read the baked MODE from the installed session-start pre-gate script.

    Returns "warn" or "block" when the script is present and parseable; "off"
    otherwise. Reads the first 20 lines so the file need not be loaded in full.
    """
    script = project_root / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh"
    if not script.exists():
        return "off"
    try:
        with script.open(encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(20))
    except OSError:
        return "off"
    if 'MODE="block"' in head:
        return "block"
    if 'MODE="warn"' in head:
        return "warn"
    return "off"


def _count_session_start_gate_violations_24h(project_root: Path) -> int:
    """Count session-start gate violations logged in the last 24 h.

    Reads ``.tapps-mcp/.session-start-gate-violations.jsonl`` and counts entries
    whose ``ts`` is within 24 hours of now. Returns 0 when the log is missing or
    unparseable — a doctor-time signal, not a gate, so failures degrade
    silently. A non-zero count means the agent reached for TappsMCP quality
    tools before tapps_session_start ran that session.
    """
    log_path = project_root / ".tapps-mcp" / ".session-start-gate-violations.jsonl"
    if not log_path.exists():
        return 0
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    count = 0
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                ts_raw = entry.get("ts", "")
                if not isinstance(ts_raw, str):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except ValueError:
                    continue
                if ts >= cutoff:
                    count += 1
    except OSError:
        return 0
    return count


def _count_cache_gate_violations_24h(project_root: Path) -> int:
    """Count cache-gate violations from the last 24 h (TAP-1224).

    Reads ``.tapps-mcp/.cache-gate-violations.jsonl`` and counts entries whose
    ``ts`` field is within 24 hours of now. Returns 0 when the log is missing
    or unparseable — this is a doctor-time signal, not a gate, so failures
    degrade silently.

    TAP-1411: only counts ``category=gate_miss`` (default for legacy entries
    without the field). ``category=cross_project`` entries are tracked
    separately and not flagged as actionable violations.
    """
    return _categorize_cache_gate_violations_24h(project_root)["gate_miss"]


def _categorize_cache_gate_violations_24h(project_root: Path) -> dict[str, int]:
    """Bucket the 24-h cache-gate violations by ``category`` (TAP-1411).

    Returns a dict with keys ``gate_miss`` and ``cross_project``. Legacy
    entries that pre-date the category field are counted as ``gate_miss``.
    """
    counts = {"gate_miss": 0, "cross_project": 0}
    log_path = project_root / ".tapps-mcp" / ".cache-gate-violations.jsonl"
    if not log_path.exists():
        return counts
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                ts_raw = entry.get("ts", "")
                if not isinstance(ts_raw, str):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
                category = entry.get("category", "gate_miss")
                if category == "cross_project":
                    counts["cross_project"] += 1
                else:
                    counts["gate_miss"] += 1
    except OSError:
        return counts
    return counts


def _host_has_deployed_skills(base: Path) -> bool:
    """True when *base* contains at least one skill with a ``SKILL.md`` file."""
    if not base.is_dir():
        return False
    return any(child.is_dir() and (child / "SKILL.md").exists() for child in base.iterdir())


def _tapps_skill_bases(project_root: Path) -> list[tuple[str, Path]]:
    """Return ``(host_label, skills_dir)`` for hosts that should be validated.

    Prefer MCP-configured hosts (``.mcp.json`` / ``.cursor/mcp.json``). Otherwise
    include hosts with deployed skills so Cursor-only projects are not forced to
    mirror Claude scaffolding.
    """
    host_mcp: dict[str, Path] = {
        "claude": project_root / ".mcp.json",
        "cursor": project_root / ".cursor" / "mcp.json",
    }
    bases: list[tuple[str, Path]] = []
    for host_label, rel in (("claude", ".claude/skills"), ("cursor", ".cursor/skills")):
        base = project_root / rel
        if host_mcp[host_label].exists() or _host_has_deployed_skills(base):
            bases.append((host_label, base))
    if not bases:
        bases.append(("claude", project_root / ".claude" / "skills"))
    return bases


def _missing_tapps_skills(project_root: Path, skill_names: tuple[str, ...]) -> list[str]:
    """List ``host/skill`` paths missing ``SKILL.md`` under each skills host."""
    missing: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        if not base.is_dir():
            missing.append(f"{host_label}: skills directory missing")
            continue
        for skill_name in skill_names:
            skill_path = base / skill_name / "SKILL.md"
            if not skill_path.exists():
                missing.append(f"{host_label}/{skill_name}")
    return missing


def _memory_skill_content_ok(skill_name: str, content: str) -> bool:
    """Reject skills that still route agents at removed ``tapps_memory`` MCP."""
    lowered = content.lower()
    if len(content.strip()) < 80:
        return False
    if "mcp__tapps-mcp__tapps_memory" in lowered:
        return False
    if skill_name == "tapps-memory":
        has_cli = "tapps-mcp memory" in lowered
        has_facade = "nlt-memory" in lowered or "tap-3895" in lowered
        return has_cli and has_facade and "tapps_session_notes" in lowered
    if skill_name == "tapps-finish-task":
        if "tapps_validate_changed" not in lowered or "tapps_checklist" not in lowered:
            return False
        return "tapps-mcp memory save" in lowered and "lookup_docs_underused" in lowered
    return False


def check_deprecated_wrapper_skills(project_root: Path) -> CheckResult:
    """Warn when v3.12.0-removed wrapper skills are still deployed (TAP-3930)."""
    from tapps_mcp.pipeline.platform_skills import DEPRECATED_TAPPS_SKILLS

    found: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        found.extend(
            f"{host_label}/{skill_name}"
            for skill_name in DEPRECATED_TAPPS_SKILLS
            if (base / skill_name / "SKILL.md").is_file()
        )
    if found:
        return CheckResult(
            "Deprecated wrapper skills",
            False,
            f"Still deployed: {', '.join(sorted(found))}",
            "Run: tapps-mcp upgrade --force — v3.12.0 removed tapps-score, "
            "tapps-gate, tapps-validate, and tapps-report. Use /tapps-finish-task "
            "and direct MCP tools instead.",
        )
    return CheckResult(
        "Deprecated wrapper skills",
        True,
        "No deprecated wrapper skills on disk",
    )


def check_finish_task_skill(project_root: Path) -> CheckResult:
    """Check the ``tapps-finish-task`` composite skill is deployed (TAP-977).

    The skill bundles validate_changed -> checklist -> optional memory.save as
    one invocation so agents don't drop steps of the closing sequence.
    """
    missing = _missing_tapps_skills(project_root, ("tapps-finish-task",))
    if missing:
        return CheckResult(
            "tapps-finish-task skill",
            False,
            f"Missing: {', '.join(missing)}",
            "Run: tapps-mcp upgrade (or upgrade --host cursor for Cursor-only projects)",
        )
    stale: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "tapps-finish-task" / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8")
            if not _memory_skill_content_ok("tapps-finish-task", content):
                stale.append(f"{host_label}/tapps-finish-task")
    if stale:
        return CheckResult(
            "tapps-finish-task skill",
            False,
            f"Stale or stub skill: {', '.join(stale)}",
            "Run: tapps-mcp upgrade --force",
        )
    hosts = ", ".join(host for host, _ in _tapps_skill_bases(project_root))
    return CheckResult(
        "tapps-finish-task skill",
        True,
        f"Present on: {hosts}",
    )


def check_tapps_memory_skill(project_root: Path) -> CheckResult:
    """Check ``tapps-memory`` skill is deployed and routes via CLI (TAP-1994)."""
    missing = _missing_tapps_skills(project_root, ("tapps-memory",))
    if missing:
        return CheckResult(
            "tapps-memory skill",
            False,
            f"Missing: {', '.join(missing)}",
            "Run: tapps-mcp upgrade --force",
        )
    stale: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "tapps-memory" / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8")
            if not _memory_skill_content_ok("tapps-memory", content):
                stale.append(f"{host_label}/tapps-memory")
    if stale:
        return CheckResult(
            "tapps-memory skill",
            False,
            f"Stale skill (missing CLI bridge or nlt-memory facade): {', '.join(stale)}",
            "Run: tapps-mcp upgrade --force",
        )
    hosts = ", ".join(host for host, _ in _tapps_skill_bases(project_root))
    return CheckResult(
        "tapps-memory skill",
        True,
        f"Present on: {hosts}",
    )


def _handoff_skill_content_ok(skill_name: str, content: str) -> bool:
    """Minimal markers proving handoff skills are functional, not empty stubs."""
    lowered = content.lower()
    if len(content.strip()) < 80:
        return False
    if "session-handoff.md" not in lowered:
        return False
    # TAP-1994: tapps_memory removed from MCP catalog — stale skills still point agents at it.
    if "mcp__tapps-mcp__tapps_memory" in lowered:
        return False
    if skill_name == "tapps-handoff-session":
        if "tapps_handoff_save" not in lowered:
            return False
        if "session_end=true" not in lowered:
            return False
        if "p0 gate" not in lowered:
            return False
        return "tapps_session_start" in lowered
    if skill_name == "tapps-continue-session":
        return (
            "tapps_session_start" in lowered
            and "memory search" in lowered
            and "p0 fallback" in lowered
        )
    return False


def check_session_handoff_skills(project_root: Path) -> CheckResult:
    """Check session-transfer skills are deployed (``tapps-handoff-session`` + ``tapps-continue-session``).

    These skills write/read ``.tapps-mcp/session-handoff.md`` via
    ``tapps_handoff_save`` (with ``session_end=true``) and
    ``tapps_session_start`` for cross-chat continuity.
    """
    skill_names = ("tapps-handoff-session", "tapps-continue-session")
    missing = _missing_tapps_skills(project_root, skill_names)
    if missing:
        return CheckResult(
            "session handoff skills",
            False,
            f"Missing: {', '.join(missing)}",
            "Run: tapps-mcp upgrade --force (or upgrade --host cursor)",
        )

    stale: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        for skill_name in skill_names:
            skill_path = base / skill_name / "SKILL.md"
            if skill_path.exists():
                content = skill_path.read_text(encoding="utf-8")
                if not _handoff_skill_content_ok(skill_name, content):
                    stale.append(f"{host_label}/{skill_name}")

    if stale:
        return CheckResult(
            "session handoff skills",
            False,
            f"Stale or stub skills: {', '.join(stale)}",
            "Run: tapps-mcp upgrade --force",
        )

    hosts = ", ".join(host for host, _ in _tapps_skill_bases(project_root))
    return CheckResult(
        "session handoff skills",
        True,
        f"tapps-handoff-session + tapps-continue-session present on: {hosts}",
    )


def check_session_handoff_schema(project_root: Path) -> CheckResult:
    """Lint ``.tapps-mcp/session-handoff.md`` for P0/Open consistency (TAP-3573)."""
    from tapps_mcp.tools.handoff_schema import handoff_path, load_and_lint_handoff

    path = handoff_path(project_root)
    if not path.is_file():
        return CheckResult(
            "session handoff schema",
            True,
            "No session-handoff.md (optional until handoff)",
        )

    _doc, lint = load_and_lint_handoff(project_root)
    if not lint.ok:
        return CheckResult(
            "session handoff schema",
            False,
            "; ".join(lint.errors),
            "Fix `.tapps-mcp/session-handoff.md` — add Next (P0) when Open has items, "
            "or invoke `/tapps-handoff-session` with a complete handoff.",
        )

    if lint.warnings:
        rel = path.name
        try:
            rel = str(path.relative_to(project_root.resolve()))
        except ValueError:
            pass
        # Non-blocking, but not a pass: an over-cap body means the cross-session
        # mirror is being rejected, and grading that "pass with a warning string"
        # is how it stayed invisible (TAP-6444, ADR-0031 warn semantics).
        return CheckResult(
            "session handoff schema",
            False,
            f"Handoff present with warnings: {'; '.join(lint.warnings)}",
            rel,
            severity="warn",
        )

    return CheckResult(
        "session handoff schema",
        True,
        "session-handoff.md schema OK",
    )
