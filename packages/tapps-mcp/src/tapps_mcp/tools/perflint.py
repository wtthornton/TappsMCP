"""Perflint performance linting wrapper.

Runs perflint (a pylint plugin) to detect Python performance anti-patterns
such as unnecessary list casts, loop-invariant statements, and inefficient
iteration patterns.

Requires ``pylint`` and ``perflint`` to be installed.  When unavailable,
all functions return empty results gracefully.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import structlog

from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)

# All perflint diagnostic codes.
PERFLINT_CODES: list[str] = [
    "W8101",  # unnecessary-list-cast
    "W8102",  # incorrect-dictionary-iterator
    "W8201",  # loop-invariant-statement
    "W8202",  # loop-global-usage
    "W8204",  # memoryview-over-bytes
    "W8205",  # dotted-import-in-loop
    "W8301",  # use-tuple-over-list
    "W8401",  # use-list-comprehension
    "W8402",  # use-list-copy
    "W8403",  # use-dict-comprehension
]

# Mapping from perflint code to internal issue label.
_CODE_TO_LABEL: dict[str, str] = {
    "W8101": "perflint_unnecessary_list_cast",
    "W8102": "perflint_incorrect_dict_iterator",
    "W8201": "perflint_loop_invariant",
    "W8202": "perflint_loop_global_usage",
    "W8204": "perflint_memoryview_over_bytes",
    "W8205": "perflint_dotted_import_in_loop",
    "W8301": "perflint_use_tuple_over_list",
    "W8401": "perflint_use_comprehension",
    "W8402": "perflint_use_comprehension",
    "W8403": "perflint_use_comprehension",
}

_PERFLINT_ARGS: list[str] = [
    "pylint",
    "--load-plugins=perflint",
    "--disable=all",
    f"--enable={','.join(PERFLINT_CODES)}",
    "--output-format=json",
]


@dataclass
class PerflintFinding:
    """A single perflint diagnostic."""

    code: str = ""
    symbol: str = ""
    message: str = ""
    file: str = ""
    line: int = 0
    column: int = 0
    label: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.label:
            self.label = _CODE_TO_LABEL.get(self.code, f"perflint_{self.symbol}")


def parse_perflint_json(raw: str) -> list[PerflintFinding]:
    """Parse pylint ``--output-format=json`` output into findings.

    Filters out pylint's own diagnostic messages (non-W8xxx codes) so
    only perflint-specific findings are returned.
    """
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    findings: list[PerflintFinding] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("message-id", ""))
        # Only keep perflint W8xxx codes
        if not code.startswith("W8"):
            continue
        findings.append(
            PerflintFinding(
                code=code,
                symbol=str(entry.get("symbol", "")),
                message=str(entry.get("message", "")),
                file=str(entry.get("path", "")),
                line=int(entry.get("line", 0)),
                column=int(entry.get("column", 0)),
            )
        )
    return findings


def run_perflint_check(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[PerflintFinding]:
    """Run perflint on a single file synchronously."""
    result = run_command(
        [*_PERFLINT_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    # pylint exits non-zero when issues found — that's expected
    return parse_perflint_json(result.stdout)


async def run_perflint_check_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[PerflintFinding]:
    """Run perflint on a single file asynchronously."""
    result = await run_command_async(
        [*_PERFLINT_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    return parse_perflint_json(result.stdout)
