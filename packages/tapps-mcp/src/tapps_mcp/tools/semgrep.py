"""Semgrep security scanner wrapper — deterministic, offline (TAP-4529).

Semgrep runs against a PINNED, in-repo ruleset (``scoring/semgrep_rules/``) and
NEVER fetches from the semgrep registry. The scorer contract (ADR-0004) forbids
any network call at scoring time, so this wrapper:

- points ``--config`` at a local file only (never ``auto`` / ``p/...`` packs),
- disables the semgrep version check and metrics upload via CLI flags AND
  environment variables (belt-and-suspenders — no incidental egress), and
- degrades gracefully: if the binary is absent or the run errors, callers get
  ``None`` and record a skipped-checker note rather than crashing the score.

Findings are tagged ``source="semgrep"`` so they carry distinct provenance from
bandit's ``B###`` findings when merged into the security section of a score.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import structlog

from tapps_mcp.scoring.models import SecurityIssue
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)

# Pinned, in-repo ruleset. Resolved relative to this file so it travels with the
# package wheel — no absolute paths, no network fetch.
SEMGREP_RULESET: Path = (
    Path(__file__).resolve().parent.parent / "scoring" / "semgrep_rules" / "tapps-security.yml"
)

# Map semgrep ERROR/WARNING/INFO to the SecurityIssue severity vocabulary.
_SEVERITY_MAP: dict[str, str] = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


def _semgrep_env() -> dict[str, str]:
    """Environment that guarantees no incidental network egress at scoring time."""
    env = os.environ.copy()
    env["SEMGREP_ENABLE_VERSION_CHECK"] = "0"
    env["SEMGREP_SEND_METRICS"] = "off"
    # Belt-and-suspenders: some semgrep versions read this too.
    env["SEMGREP_METRICS"] = "off"
    return env


def _semgrep_args(file_path: str) -> list[str]:
    """Build the semgrep argv — pinned local config, JSON out, offline flags."""
    return [
        "semgrep",
        "scan",
        "--config",
        str(SEMGREP_RULESET),
        "--json",
        "--quiet",
        "--disable-version-check",
        "--metrics=off",
        "--no-git-ignore",
        file_path,
    ]


def semgrep_available() -> bool:
    """Return True when the semgrep binary is on PATH and the ruleset exists."""
    return shutil.which("semgrep") is not None and SEMGREP_RULESET.is_file()


def parse_semgrep_json(raw: str) -> list[SecurityIssue] | None:
    """Parse semgrep ``--json`` output into ``SecurityIssue`` models.

    Returns ``None`` when output is empty or unparseable (skipped/parse failure).
    Returns ``[]`` when semgrep ran cleanly and found nothing.
    """
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    results = data.get("results", [])
    if not isinstance(results, list):
        return []
    issues: list[SecurityIssue] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        extra = r.get("extra", {}) if isinstance(r.get("extra"), dict) else {}
        metadata = extra.get("metadata", {}) if isinstance(extra.get("metadata"), dict) else {}
        start = r.get("start", {}) if isinstance(r.get("start"), dict) else {}
        sem_sev = str(extra.get("severity", "WARNING")).upper()
        issues.append(
            SecurityIssue(
                code=str(r.get("check_id", "semgrep.unknown")),
                message=str(extra.get("message", "")).strip(),
                file=str(r.get("path", "")),
                line=int(start.get("line", 0) or 0),
                severity=_SEVERITY_MAP.get(sem_sev, "medium"),
                confidence="high",
                owasp=_owasp_from_metadata(metadata),
                source="semgrep",
            )
        )
    return issues


def _owasp_from_metadata(metadata: dict[str, object]) -> str | None:
    """Pull the OWASP category out of a rule's metadata block, if present."""
    owasp = metadata.get("owasp")
    if isinstance(owasp, str):
        return owasp
    if isinstance(owasp, list) and owasp and isinstance(owasp[0], str):
        return owasp[0]
    return None


def run_semgrep_check(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[SecurityIssue] | None:
    """Run semgrep on a single file synchronously against the pinned ruleset.

    Returns ``None`` when semgrep is unavailable or produced no usable output
    (graceful skip). Returns ``[]`` when it ran and found nothing.
    """
    if not semgrep_available():
        logger.info("semgrep_not_available", hint="pip install semgrep")
        return None
    result = run_command(
        _semgrep_args(file_path),
        cwd=cwd,
        timeout=timeout,
        env=_semgrep_env(),
    )
    if result.returncode < 0:  # not-found / timeout sentinel from run_command
        return None
    return parse_semgrep_json(result.stdout)


async def run_semgrep_check_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[SecurityIssue] | None:
    """Run semgrep on a single file asynchronously against the pinned ruleset.

    Returns ``None`` when semgrep is unavailable or produced no usable output
    (graceful skip). Returns ``[]`` when it ran and found nothing.
    """
    if not semgrep_available():
        logger.info("semgrep_not_available", hint="pip install semgrep")
        return None
    result = await run_command_async(
        _semgrep_args(file_path),
        cwd=cwd,
        timeout=timeout,
        env=_semgrep_env(),
    )
    if result.returncode < 0:
        return None
    return parse_semgrep_json(result.stdout)
