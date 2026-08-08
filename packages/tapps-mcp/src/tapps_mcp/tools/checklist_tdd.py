"""TDD stage validation for ``tapps_checklist`` (TAP-476).

Checks the red / green / refactor commit sequence and the coverage floor.
Split out of ``checklist.py``.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# TDD stage validation (TAP-476)
# ---------------------------------------------------------------------------

_TDD_RED_PREFIXES = ("test:", "tests:")
_TDD_GREEN_PREFIXES = ("fix:", "feat:")
_TDD_REFACTOR_PREFIXES = ("refactor:", "chore:")
_COVERAGE_MIN = 80.0


class TDDStageCheck(BaseModel):
    """Result of a single TDD stage check."""

    stage: str = Field(description="TDD stage name: red | green | refactor | coverage")
    result: str = Field(description="passed | failed | skipped")
    message: str = Field(default="", description="Human-readable explanation.")


class TDDCheckResult(BaseModel):
    """Aggregate result of TDD stage validation."""

    checks: list[TDDStageCheck] = Field(default_factory=list)
    passed: bool = Field(description="True only when all non-skipped checks pass.")
    summary: str = Field(default="", description="One-line summary.")


_COMPILE_SKIP_DIRS = frozenset(
    {
        ".venv",
        "__pycache__",
        ".git",
        "node_modules",
        ".tox",
        "site-packages",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        "vendor",
        ".eggs",
        ".pytest_cache",
    }
)


def _compile_scan_roots(repo_root: Path) -> list[Path]:
    """Prefer project source trees over a full-repo rglob."""
    roots: list[Path] = []
    src = repo_root / "src"
    if src.is_dir():
        roots.append(src)
    packages = repo_root / "packages"
    if packages.is_dir():
        for pkg in packages.iterdir():
            pkg_src = pkg / "src"
            if pkg_src.is_dir():
                roots.append(pkg_src)
    return roots or [repo_root]


def _check_compile_time_red(repo_root: Path) -> TDDStageCheck:
    """Validate that RED state is runtime RED (test failure) not compile-time RED.

    Compile-time RED means a syntax/import error that prevents even running
    pytest — that is invalid TDD RED state.  We check whether any Python file
    under project source roots is unparseable (skipping venv/vendor caches).
    """
    import ast

    broken: list[str] = []
    for scan_root in _compile_scan_roots(repo_root):
        for py_file in scan_root.rglob("*.py"):
            if any(part in _COMPILE_SKIP_DIRS for part in py_file.parts):
                continue
            try:
                ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                try:
                    broken.append(str(py_file.relative_to(repo_root)))
                except ValueError:
                    broken.append(py_file.name)
            if len(broken) >= 3:
                break
        if len(broken) >= 3:
            break

    if broken:
        return TDDStageCheck(
            stage="red_state",
            result="failed",
            message=(
                f"Compile-time RED detected — syntax errors in: {', '.join(broken)}. "
                "Fix syntax before committing RED checkpoint."
            ),
        )
    return TDDStageCheck(
        stage="red_state",
        result="passed",
        message="No compile-time errors found; RED state is valid runtime RED.",
    )


def _all_stages_skipped(message: str) -> list[TDDStageCheck]:
    """RED / GREEN / REFACTOR all skipped for the same reason."""
    return [
        TDDStageCheck(stage=stage, result="skipped", message=message)
        for stage in ("red", "green", "refactor")
    ]


def _has_commit_prefix(lines: list[str], prefixes: tuple[str, ...]) -> bool:
    """True when any ``git log --oneline`` line's message starts with a prefix."""
    return any(
        # git log --oneline format: "<sha> <message>"
        " ".join(ln.split()[1:]).lower().startswith(pfx)
        for ln in lines
        for pfx in prefixes
    )


def _stage_check(
    stage: str, ok: bool, found: str, missing: str, *, missing_result: str
) -> TDDStageCheck:
    """One TDD stage verdict. *missing_result* is failed, or skipped when optional."""
    return TDDStageCheck(
        stage=stage,
        result="passed" if ok else missing_result,
        message=found if ok else missing,
    )


async def _check_git_commits(
    red_prefixes: tuple[str, ...],
    green_prefixes: tuple[str, ...],
    refactor_prefixes: tuple[str, ...],
) -> list[TDDStageCheck]:
    """Scan recent git log for RED/GREEN/REFACTOR checkpoint commits."""
    from tapps_mcp.tools.subprocess_runner import run_command_async

    try:
        result = await run_command_async(["git", "log", "--oneline", "-30"], timeout=5)
        if result.returncode != 0:
            return _all_stages_skipped("git log unavailable.")
        log_lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    except Exception:
        return _all_stages_skipped("git not available.")

    return [
        _stage_check(
            "red",
            _has_commit_prefix(log_lines, red_prefixes),
            "RED checkpoint commit found (test: prefix).",
            "No RED checkpoint commit found. Expected a commit starting with 'test:'.",
            missing_result="failed",
        ),
        _stage_check(
            "green",
            _has_commit_prefix(log_lines, green_prefixes),
            "GREEN checkpoint commit found (fix:/feat: prefix).",
            "No GREEN checkpoint found. Expected a commit starting with 'fix:' or 'feat:'.",
            missing_result="failed",
        ),
        _stage_check(
            "refactor",
            _has_commit_prefix(log_lines, refactor_prefixes),
            "REFACTOR checkpoint commit found.",
            "No REFACTOR checkpoint found (optional — skipped).",
            missing_result="skipped",
        ),
    ]


def _check_coverage(repo_root: Path) -> TDDStageCheck:
    """Check coverage threshold from .coverage or coverage.xml."""
    from defusedxml.ElementTree import parse as parse_xml

    # Try coverage.xml first (generated by pytest-cov --cov-report=xml)
    xml_path = repo_root / "coverage.xml"
    if xml_path.exists():
        try:
            tree = parse_xml(xml_path)
            root_el = tree.getroot()
            line_rate = float(root_el.attrib.get("line-rate", "0"))
            pct = round(line_rate * 100, 1)
            passed = pct >= _COVERAGE_MIN
            return TDDStageCheck(
                stage="coverage",
                result="passed" if passed else "failed",
                message=(
                    f"Coverage {pct}% {'meets' if passed else 'below'} "
                    f"{_COVERAGE_MIN}% threshold (from coverage.xml)."
                ),
            )
        except Exception:
            logger.debug("coverage_xml_parse_failed", path=str(xml_path), exc_info=True)

    # Try .coverage binary presence as a weak signal
    dot_coverage = repo_root / ".coverage"
    if dot_coverage.exists():
        return TDDStageCheck(
            stage="coverage",
            result="skipped",
            message=".coverage file exists but cannot be parsed without coverage.py CLI. "
            "Run `coverage report` to verify >= 80%.",
        )

    return TDDStageCheck(
        stage="coverage",
        result="skipped",
        message="No coverage.xml or .coverage found. "
        "Run pytest with --cov --cov-report=xml to generate coverage data.",
    )


async def check_tdd_stages(repo_root: Path | None = None) -> TDDCheckResult:
    """Run all TDD stage checks and return an aggregate result.

    Args:
        repo_root: Root of the repository. Defaults to cwd.
    """
    root = repo_root or Path.cwd()

    compile_check = _check_compile_time_red(root)
    git_checks = await _check_git_commits(
        _TDD_RED_PREFIXES, _TDD_GREEN_PREFIXES, _TDD_REFACTOR_PREFIXES
    )
    coverage_check = _check_coverage(root)

    all_checks = [compile_check, *git_checks, coverage_check]

    failed = [c for c in all_checks if c.result == "failed"]
    passed_all = len(failed) == 0

    summary = (
        "All TDD stage checks passed."
        if passed_all
        else f"{len(failed)} TDD stage check(s) failed: {', '.join(c.stage for c in failed)}."
    )

    return TDDCheckResult(checks=all_checks, passed=passed_all, summary=summary)
