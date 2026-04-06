"""Vulture dead code detection wrapper.

Detects unused functions, classes, imports, variables, attributes,
and unreachable code using the vulture static analysis tool.  Falls
back gracefully (empty results) when vulture is not installed.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from tapps_mcp.tools.subprocess_runner import run_command_async

logger = structlog.get_logger(__name__)

# Regex to parse vulture's text output.
# Format: "path.py:42: unused function 'helper' (60% confidence)"
_VULTURE_LINE_RE = re.compile(r"^(.+):(\d+): unused ([\w\s]+) '([^']+)' \((\d+)% confidence\)$")

# Unreachable code has a different format:
# "path.py:42: unreachable code after 'return' (100% confidence)"
_VULTURE_UNREACHABLE_RE = re.compile(
    r"^(.+):(\d+): unreachable code after '([^']+)' \((\d+)% confidence\)$"
)

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

        # Try the standard "unused <type> '<name>'" pattern first
        match = _VULTURE_LINE_RE.match(stripped)
        if match:
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
            continue

        # Try the "unreachable code after '<keyword>'" pattern
        unreach = _VULTURE_UNREACHABLE_RE.match(stripped)
        if unreach:
            file_path = unreach.group(1)
            line_no = int(unreach.group(2))
            keyword = unreach.group(3)
            confidence = int(unreach.group(4))

            if confidence < min_confidence:
                continue

            findings.append(
                DeadCodeFinding(
                    file_path=file_path,
                    line=line_no,
                    name=keyword,
                    finding_type="unreachable_code",
                    confidence=confidence,
                    message=f"unreachable code after '{keyword}' ({confidence}% confidence)",
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


# ---------------------------------------------------------------------------
# Multi-file / project-wide support
# ---------------------------------------------------------------------------

_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".venv", "venv", "env", "ENV", "__pycache__", ".git", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules", ".tox",
    "dist", "build", ".eggs", "htmlcov", ".tapps-agents",
    ".tapps-mcp-cache", "site-packages",
})

_GIT_DIFF_TIMEOUT = 5


@dataclass
class DeadCodeResult:
    """Aggregate result from a multi-file dead code scan."""

    findings: list[DeadCodeFinding] = field(default_factory=list)
    files_scanned: int = 0
    degraded: bool = False


def collect_python_files(project_root: Path) -> list[str]:
    """Collect all .py files under project_root, excluding common non-source dirs.

    Args:
        project_root: Root directory to scan.

    Returns:
        List of relative path strings.
    """
    result: list[str] = []
    for path in sorted(project_root.rglob("*.py")):
        # Skip excluded directories (exact match or .venv* prefix)
        parts = path.relative_to(project_root).parts
        if any(
            part in _EXCLUDED_DIRS or part.startswith(".venv")
            for part in parts
        ):
            continue
        result.append(str(path.relative_to(project_root)))
    return result


def collect_changed_python_files(project_root: Path) -> list[str]:
    """Collect changed .py files using git diff (unstaged + staged).

    Args:
        project_root: Git repository root.

    Returns:
        Sorted list of relative path strings for changed .py files that exist.
    """
    files: set[str] = set()
    for extra_args in (["HEAD"], ["--cached"]):
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", *extra_args],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=_GIT_DIFF_TIMEOUT,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                files.update(result.stdout.strip().splitlines())
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    py_files: list[str] = []
    for f in sorted(files):
        if f.endswith(".py") and (project_root / f).is_file():
            py_files.append(f)
    return py_files


def clamp_confidence(value: int) -> int:
    """Clamp min_confidence to the valid 0-100 range."""
    return max(0, min(100, value))


async def run_vulture_multi_async(
    file_paths: list[str],
    *,
    min_confidence: int = 80,
    whitelist_patterns: list[str] | None = None,
    cwd: str | None = None,
    timeout: int = 60,
) -> DeadCodeResult:
    """Run vulture on multiple files at once for cross-file analysis.

    Args:
        file_paths: List of file paths to analyse.
        min_confidence: Minimum confidence percentage (0-100).
        whitelist_patterns: File name patterns to exclude (fnmatch on basename).
        cwd: Working directory for the subprocess.
        timeout: Timeout in seconds.

    Returns:
        DeadCodeResult with findings, file count, and degraded flag.
    """
    min_confidence = clamp_confidence(min_confidence)

    if not file_paths:
        return DeadCodeResult(files_scanned=0)

    if not is_vulture_available():
        logger.debug("vulture_not_installed")
        return DeadCodeResult(files_scanned=len(file_paths), degraded=True)

    cmd = [
        "vulture",
        *file_paths,
        f"--min-confidence={min_confidence}",
    ]

    result = await run_command_async(cmd, cwd=cwd, timeout=timeout)

    if result.timed_out:
        logger.warning("vulture_timeout_multi", file_count=len(file_paths), timeout=timeout)
        return DeadCodeResult(files_scanned=len(file_paths))

    findings = parse_vulture_output(result.stdout, min_confidence=min_confidence)

    if whitelist_patterns:
        findings = [f for f in findings if not _matches_whitelist(f.file_path, whitelist_patterns)]

    return DeadCodeResult(
        findings=findings,
        files_scanned=len(file_paths),
    )
