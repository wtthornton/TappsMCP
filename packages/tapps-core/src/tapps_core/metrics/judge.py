"""Judge pattern for tapps_validate_changed (TAP-478).

Provides declarative pass/fail criteria (pytest, grep, exists) that run
alongside the quality gate.  Stolen from the ECC eval-harness skill.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

_logger = structlog.get_logger(__name__)

JudgeType = Literal["pytest", "grep", "exists"]


class JudgeDefinition(BaseModel):
    """A single declarative pass/fail criterion."""

    type: JudgeType = Field(description="Judge type: pytest | grep | exists")
    target: str = Field(
        description=(
            "For pytest: pytest target (e.g. 'tests/unit/', 'tests/unit/test_foo.py'). "
            "For grep: file path to search. "
            "For exists: file path that must exist."
        )
    )
    expect: str = Field(
        default="",
        description=(
            "For pytest: ignored (exit 0 = pass). "
            "For grep: regex pattern that must match at least one line. "
            "For exists: ignored (path must exist)."
        ),
    )
    description: str = Field(
        default="",
        description="Human-readable description of what this judge verifies.",
    )
    blocking: bool = Field(
        default=False,
        description="When True, judge failure counts as an overall validation failure. "
        "Default False (advisory only) for v1.",
    )


class JudgeResult(BaseModel):
    """Result of a single judge run."""

    judge: str = Field(description="Judge description or type:target key.")
    type: JudgeType
    result: Literal["pass", "fail", "error"]
    message: str = Field(default="")
    blocking: bool = Field(default=False)


async def run_judge(jd: JudgeDefinition, cwd: Path | None = None) -> JudgeResult:
    """Execute a single JudgeDefinition and return its result.

    Args:
        jd: The judge definition to execute.
        cwd: Working directory for subprocess judges (pytest). Defaults to cwd.
    """
    label = jd.description or f"{jd.type}:{jd.target}"
    work_dir = cwd or Path.cwd()

    if jd.type == "exists":
        return await _run_exists_judge(jd, label)
    if jd.type == "grep":
        return await _run_grep_judge(jd, label)
    if jd.type == "pytest":
        return await _run_pytest_judge(jd, label, work_dir)

    return JudgeResult(
        judge=label,
        type=jd.type,
        result="error",
        message=f"Unknown judge type: {jd.type!r}",
        blocking=jd.blocking,
    )


async def _run_exists_judge(jd: JudgeDefinition, label: str) -> JudgeResult:
    path = Path(jd.target)
    exists = path.exists()
    return JudgeResult(
        judge=label,
        type="exists",
        result="pass" if exists else "fail",
        message=f"{'Found' if exists else 'Missing'}: {jd.target}",
        blocking=jd.blocking,
    )


async def _run_grep_judge(jd: JudgeDefinition, label: str) -> JudgeResult:
    file_path = Path(jd.target)
    if not file_path.exists():
        return JudgeResult(
            judge=label,
            type="grep",
            result="fail",
            message=f"File not found: {jd.target}",
            blocking=jd.blocking,
        )
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        matched = bool(re.search(jd.expect, text, re.MULTILINE))
        return JudgeResult(
            judge=label,
            type="grep",
            result="pass" if matched else "fail",
            message=(
                f"Pattern {jd.expect!r} {'matched' if matched else 'not found'} in {jd.target}"
            ),
            blocking=jd.blocking,
        )
    except Exception as exc:
        return JudgeResult(
            judge=label,
            type="grep",
            result="error",
            message=f"Error reading {jd.target}: {exc}",
            blocking=jd.blocking,
        )


async def _run_pytest_judge(jd: JudgeDefinition, label: str, cwd: Path) -> JudgeResult:
    try:
        proc = await asyncio.create_subprocess_exec(
            "python",
            "-m",
            "pytest",
            jd.target,
            "--tb=no",
            "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except TimeoutError:
            proc.kill()
            return JudgeResult(
                judge=label,
                type="pytest",
                result="error",
                message=f"pytest timed out after 120s for target: {jd.target}",
                blocking=jd.blocking,
            )

        passed = proc.returncode == 0
        err_hint = stderr.decode(errors="replace").strip()[-200:] if stderr else ""
        return JudgeResult(
            judge=label,
            type="pytest",
            result="pass" if passed else "fail",
            message=(
                f"pytest exit {proc.returncode} for {jd.target}"
                + (f": {err_hint}" if err_hint and not passed else "")
            ),
            blocking=jd.blocking,
        )
    except FileNotFoundError:
        return JudgeResult(
            judge=label,
            type="pytest",
            result="error",
            message="python -m pytest not found. Is pytest installed in this environment?",
            blocking=jd.blocking,
        )
    except Exception as exc:
        return JudgeResult(
            judge=label,
            type="pytest",
            result="error",
            message=f"Unexpected error running pytest: {exc}",
            blocking=jd.blocking,
        )


async def run_judges(
    definitions: list[dict[str, Any]],
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Run a list of raw judge dicts and return aggregated results.

    Args:
        definitions: List of dicts matching JudgeDefinition fields.
        cwd: Working directory for subprocess judges.

    Returns:
        Dict with ``judge_results`` list and ``judges_passed`` bool.
    """
    if not definitions:
        return {"judge_results": [], "judges_passed": True}

    parsed: list[JudgeDefinition] = []
    parse_errors: list[str] = []
    for raw in definitions:
        try:
            parsed.append(JudgeDefinition.model_validate(raw))
        except Exception as exc:
            parse_errors.append(str(exc))

    if parse_errors:
        return {
            "judge_results": [],
            "judges_passed": False,
            "judge_parse_errors": parse_errors,
        }

    results = await asyncio.gather(*[run_judge(jd, cwd) for jd in parsed])

    any_blocking_fail = any(r.result in {"fail", "error"} and r.blocking for r in results)

    return {
        "judge_results": [r.model_dump() for r in results],
        "judges_passed": not any_blocking_fail,
    }
