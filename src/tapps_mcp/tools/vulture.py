"""Vulture dead code detection wrapper.

Detects unused functions, classes, imports, variables, attributes,
and unreachable code using the vulture static analysis tool.  Falls
back gracefully (empty results) when vulture is not installed.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import structlog

from tapps_mcp.tools.subprocess_runner import run_command_async

logger = structlog.get_logger(__name__)

# Regex to parse vulture's text output.
# Format: "path.py:42: unused function 'helper' (60% confidence)"
_VULTURE_LINE_RE = re.compile(r"^(.+):(\d+): unused ([\w\s]+) '([^']+)' \((\d+)% confidence\)$")

# Map vulture description words to normalised finding types.
_TYPE_MAP: dict[str, str] = {
    "function": "function",
    "class": "class",
    "import": "import",
    "variable": "variable",
    "attribute": "attribute",
    "property": "attribute",
    "unreachable code": "unreachable_code",
}


@dataclass
class DeadCodeFinding:
    """A single dead-code finding reported by vulture."""

    file_path: str = ""
    line: int = 0
    name: str = ""
    finding_type: str = ""  # function | class | import | variable | unreachable_code | attribute
    confidence: int = 0  # 0-100
    message: str = ""


def _normalise_finding_type(raw: str) -> str:
    """Normalise the finding type extracted from vulture output."""
    raw_lower = raw.strip().lower()
    if raw_lower in _TYPE_MAP:
        return _TYPE_MAP[raw_lower]
    # Handle multi-word types that contain a known key
    for key, value in _TYPE_MAP.items():
        if key in raw_lower:
            return value
    return raw_lower


def parse_vulture_output(
    raw: str,
    *,
    min_confidence: int = 0,
) -> list[DeadCodeFinding]:
    """Parse vulture text output into structured findings.

    Args:
        raw: Raw stdout from vulture.
        min_confidence: Minimum confidence threshold (0-100).

    Returns:
        List of parsed findings above the confidence threshold.
    """
    if not raw.strip():
        return []

    findings: list[DeadCodeFinding] = []
    for raw_line in raw.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _VULTURE_LINE_RE.match(stripped)
        if not match:
            continue
        file_path = match.group(1)
        line_no = int(match.group(2))
        raw_type = match.group(3)
        name = match.group(4)
        confidence = int(match.group(5))

        if confidence < min_confidence:
            continue

        finding_type = _normalise_finding_type(raw_type)
        findings.append(
            DeadCodeFinding(
                file_path=file_path,
                line=line_no,
                name=name,
                finding_type=finding_type,
                confidence=confidence,
                message=f"unused {raw_type.strip()} '{name}' ({confidence}% confidence)",
            )
        )
    return findings


def is_vulture_available() -> bool:
    """Check whether the vulture executable is on PATH."""
    return shutil.which("vulture") is not None


def _matches_whitelist(file_path: str, patterns: list[str]) -> bool:
    """Return True if file_path matches any whitelist pattern (fnmatch on basename)."""
    if not patterns:
        return False
    base = Path(file_path).name
    return any(fnmatch.fnmatch(base, p) for p in patterns)


async def run_vulture_async(
    file_path: str,
    *,
    min_confidence: int = 80,
    whitelist_patterns: list[str] | None = None,
    cwd: str | None = None,
    timeout: int = 30,
) -> list[DeadCodeFinding]:
    """Run vulture on a single file asynchronously.

    Args:
        file_path: Path to the Python file to analyse.
        min_confidence: Minimum confidence percentage (0-100).
        whitelist_patterns: File name patterns to exclude (fnmatch on basename).
        cwd: Working directory for the subprocess.
        timeout: Timeout in seconds.

    Returns:
        List of dead-code findings, or empty list if vulture
        is not installed or an error occurs.
    """
    if not is_vulture_available():
        logger.debug("vulture_not_installed")
        return []

    cmd = [
        "vulture",
        file_path,
        f"--min-confidence={min_confidence}",
    ]

    result = await run_command_async(cmd, cwd=cwd, timeout=timeout)

    if result.timed_out:
        logger.warning("vulture_timeout", file=file_path, timeout=timeout)
        return []

    # vulture exits 0 when no dead code found, non-zero when findings exist.
    # Both are valid; we just parse stdout.
    findings = parse_vulture_output(result.stdout, min_confidence=min_confidence)

    # Filter by whitelist patterns (e.g. test_*, conftest.py)
    if whitelist_patterns:
        findings = [f for f in findings if not _matches_whitelist(f.file_path, whitelist_patterns)]

    return findings
