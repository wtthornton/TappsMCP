"""mypy type-checker wrapper — scoped single-file execution."""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from tapps_mcp.scoring.models import TypeIssue
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)

# Match ``path:line: severity: message``, including Windows drive-letter paths
# like ``C:\\foo\\bar.py:10: error: …`` (naive ``split(":", 3)`` breaks those).
_MYPY_LINE_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):\s*(?P<severity>error|warning|note)\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)


def parse_mypy_output(raw: str, target_file: str | None = None) -> list[TypeIssue]:
    """Parse mypy plain-text output into ``TypeIssue`` models.

    Each line looks like::

        path/to/file.py:10: error: Incompatible types [assignment]
    """
    # Pre-compute resolved target path once for efficient per-line comparison.
    _target_resolved: Path | None = Path(target_file).resolve() if target_file else None

    issues: list[TypeIssue] = []
    for line in raw.strip().splitlines():
        if (
            "error:" not in line.lower()
            and "warning:" not in line.lower()
            and "note:" not in line.lower()
        ):
            continue
        m = _MYPY_LINE_RE.match(line)
        if m is None:
            continue
        filename = m.group("file").strip()
        # Filter to target file if specified.
        # Use Path.resolve() for robust comparison that handles absolute/relative
        # mismatches: mypy may emit a relative path (e.g. "src/foo.py") even when
        # invoked with an absolute target path ("/abs/path/src/foo.py").
        # The old substring check silently dropped all findings in that case.
        if _target_resolved is not None:
            try:
                filename_resolved = Path(filename).resolve()
            except OSError:
                filename_resolved = Path(filename)
            # Primary check: resolved absolute-path equality.
            if filename_resolved != _target_resolved:
                # Fallback: suffix match for when the mypy-emitted filename is a
                # relative path whose CWD differs from the Python process CWD.
                # Example: target="/abs/src/foo.py", mypy emits "src/foo.py".
                # Normalize separators so Windows ``\`` paths still match.
                target_str = str(_target_resolved).replace("\\", "/")
                filename_norm = filename.replace("\\", "/")
                if not (target_str.endswith("/" + filename_norm) or target_str == filename_norm):
                    continue
        line_num = int(m.group("line"))
        severity_raw = m.group("severity").strip().lower()
        message = m.group("message").strip()

        # Extract error code from brackets
        error_code: str | None = None
        if "[" in message and "]" in message:
            start = message.rfind("[")
            end = message.rfind("]")
            if start < end:
                error_code = message[start + 1 : end]
                message = message[:start].strip()

        if "error" in severity_raw:
            severity = "error"
        elif "warning" in severity_raw:
            severity = "warning"
        else:
            severity = "note"

        issues.append(
            TypeIssue(
                file=filename,
                line=line_num,
                message=message,
                error_code=error_code,
                severity=severity,
            )
        )
    return issues


def calculate_type_score(issues: list[TypeIssue]) -> float:
    """Convert type issues into a 0-10 score."""
    from tapps_mcp.scoring.constants import MYPY_ERROR_PENALTY, clamp_individual

    error_count = sum(1 for i in issues if i.severity == "error")
    score = 10.0 - (error_count * MYPY_ERROR_PENALTY)
    return clamp_individual(score)


_MYPY_ARGS: list[str] = [
    "mypy",
    "--show-error-codes",
    "--no-error-summary",
    "--no-color-output",
    "--no-incremental",
    "--follow-imports=skip",
]


def run_mypy_check(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[TypeIssue] | None:
    """Run scoped mypy on a single file synchronously.

    Returns ``None`` on timeout or when the tool cannot produce usable output
    (callers must treat that as degraded, not as a clean zero-issue result).
    """
    result = run_command(
        [*_MYPY_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if result.timed_out:
        logger.warning("mypy_timeout", file=file_path, timeout=timeout)
        return None
    return parse_mypy_output(result.stdout, target_file=file_path)


async def run_mypy_check_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[TypeIssue] | None:
    """Run scoped mypy on a single file asynchronously.

    Returns ``None`` on timeout (degraded signal for callers).
    """
    result = await run_command_async(
        [*_MYPY_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if result.timed_out:
        logger.warning("mypy_timeout_async", file=file_path, timeout=timeout)
        return None
    return parse_mypy_output(result.stdout, target_file=file_path)
