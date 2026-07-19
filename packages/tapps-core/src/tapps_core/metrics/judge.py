"""Judge pattern for tapps_validate_changed (TAP-478).

Provides declarative pass/fail criteria (pytest, grep, exists, shell) that run
alongside the quality gate.  Stolen from the ECC eval-harness skill.
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field, field_validator

_logger = structlog.get_logger(__name__)

JudgeType = Literal["pytest", "grep", "exists", "shell", "command"]
JudgeOutcome = Literal["pass", "fail", "error", "skipped"]


class JudgeDefinition(BaseModel):
    """A single declarative pass/fail criterion."""

    type: JudgeType = Field(description="Judge type: pytest | grep | exists | shell | command")
    target: str = Field(
        description=(
            "For pytest: pytest target (e.g. 'tests/unit/', 'tests/unit/test_foo.py'). "
            "For grep: file path to search. "
            "For exists: file path that must exist. "
            "For shell/command: command string to execute."
        )
    )
    expect: str = Field(
        default="",
        description=(
            "For pytest: ignored (exit 0 = pass). "
            "For grep: regex pattern that must match at least one line. "
            "For exists: ignored (path must exist). "
            "For shell/command: ignored (exit code 0 = pass)."
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
    when_changed: list[str] = Field(
        default_factory=list,
        description="Optional glob list. Judge runs only when a changed path matches.",
    )
    timeout_s: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Timeout for shell/command judges (seconds).",
    )
    command: str = Field(
        default="",
        description=(
            "For pytest: optional command prefix override (e.g. 'uv run pytest'). "
            "When set, skips auto-resolution. "
            "For other types: unused."
        ),
    )

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_shell_alias(cls, value: object) -> object:
        if value == "command":
            return "shell"
        return value


class JudgeResult(BaseModel):
    """Result of a single judge run."""

    judge: str = Field(description="Judge description or type:target key.")
    type: JudgeType
    result: JudgeOutcome
    message: str = Field(default="")
    blocking: bool = Field(default=False)


def _path_matches_glob(path: str, pattern: str) -> bool:
    normalised = path.replace("\\", "/")
    return fnmatch.fnmatch(normalised, pattern)


def _should_run_judge(jd: JudgeDefinition, changed_paths: list[str] | None) -> bool:
    if not jd.when_changed:
        return True
    if not changed_paths:
        return True
    return any(
        _path_matches_glob(changed, pattern)
        for changed in changed_paths
        for pattern in jd.when_changed
    )


def _git_changed_paths(cwd: Path, base_ref: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


async def run_judge(
    jd: JudgeDefinition,
    cwd: Path | None = None,
    *,
    changed_paths: list[str] | None = None,
) -> JudgeResult:
    """Execute a single JudgeDefinition and return its result."""
    label = jd.description or f"{jd.type}:{jd.target}"
    work_dir = cwd or Path.cwd()

    if not _should_run_judge(jd, changed_paths):
        return JudgeResult(
            judge=label,
            type=jd.type,
            result="skipped",
            message="Skipped: no changed paths matched when_changed globs",
            blocking=jd.blocking,
        )

    if jd.type == "exists":
        return await _run_exists_judge(jd, label, work_dir)
    if jd.type == "grep":
        return await _run_grep_judge(jd, label, work_dir)
    if jd.type == "pytest":
        return await _run_pytest_judge(jd, label, work_dir)
    if jd.type == "shell":
        return await _run_shell_judge(jd, label, work_dir)

    return JudgeResult(
        judge=label,
        type=jd.type,
        result="error",
        message=f"Unknown judge type: {jd.type!r}",
        blocking=jd.blocking,
    )


async def _run_exists_judge(jd: JudgeDefinition, label: str, cwd: Path) -> JudgeResult:
    path = Path(jd.target)
    if not path.is_absolute():
        path = cwd / path
    exists = path.exists()
    return JudgeResult(
        judge=label,
        type="exists",
        result="pass" if exists else "fail",
        message=f"{'Found' if exists else 'Missing'}: {jd.target}",
        blocking=jd.blocking,
    )


def _grep_searchable_text(text: str) -> str:
    """Return file text with whole-line comments stripped for grep judges."""
    lines: list[str] = []
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line
        stripped = line.strip()
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block = True
            continue
        if stripped.startswith(("//", "#")):
            continue
        if "//" in line:
            line = line[: line.index("//")]
        lines.append(line)
    return "\n".join(lines)


async def _run_grep_judge(jd: JudgeDefinition, label: str, cwd: Path) -> JudgeResult:
    file_path = Path(jd.target)
    if not file_path.is_absolute():
        file_path = cwd / file_path
    if not file_path.exists():
        return JudgeResult(
            judge=label,
            type="grep",
            result="fail",
            message=f"File not found: {jd.target}",
            blocking=jd.blocking,
        )
    try:
        text = _grep_searchable_text(file_path.read_text(encoding="utf-8", errors="replace"))
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


def _project_venv_python(cwd: Path) -> Path | None:
    for candidate in (cwd / ".venv" / "bin" / "python", cwd / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    return None


def _pytest_argv_candidates(jd: JudgeDefinition, cwd: Path) -> tuple[list[list[str]], list[str]]:
    """Return pytest argv lists to try and human-readable strategy labels."""
    target = jd.target
    flags = ["--tb=no", "-q"]

    if jd.command.strip():
        base = shlex.split(jd.command)
        if target in jd.command:
            return [base], [jd.command.strip()]
        return [[*base, target, *flags]], [jd.command.strip()]

    strategies: list[tuple[str, list[str]]] = [
        ("uv run pytest", ["uv", "run", "pytest", target, *flags]),
    ]
    venv_python = _project_venv_python(cwd)
    if venv_python is not None:
        strategies.append(
            (
                f"{venv_python} -m pytest",
                [str(venv_python), "-m", "pytest", target, *flags],
            )
        )
    strategies.append(("python -m pytest", ["python", "-m", "pytest", target, *flags]))
    return [argv for _, argv in strategies], [name for name, _ in strategies]


async def _run_pytest_judge(jd: JudgeDefinition, label: str, cwd: Path) -> JudgeResult:
    argvs, strategy_labels = _pytest_argv_candidates(jd, cwd)
    attempted: list[str] = []

    for argv, strategy in zip(argvs, strategy_labels, strict=True):
        attempted.append(strategy)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
        except FileNotFoundError:
            continue
        except Exception as exc:
            return JudgeResult(
                judge=label,
                type="pytest",
                result="error",
                message=f"Unexpected error running pytest ({strategy}): {exc}",
                blocking=jd.blocking,
            )

        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except TimeoutError:
            proc.kill()
            return JudgeResult(
                judge=label,
                type="pytest",
                result="error",
                message=f"pytest timed out after 120s ({strategy}) for target: {jd.target}",
                blocking=jd.blocking,
            )

        passed = proc.returncode == 0
        err_hint = stderr.decode(errors="replace").strip()[-200:] if stderr else ""
        return JudgeResult(
            judge=label,
            type="pytest",
            result="pass" if passed else "fail",
            message=(
                f"pytest ({strategy}) exit {proc.returncode} for {jd.target}"
                + (f": {err_hint}" if err_hint and not passed else "")
            ),
            blocking=jd.blocking,
        )

    tried = ", ".join(attempted) if attempted else "none"
    return JudgeResult(
        judge=label,
        type="pytest",
        result="error",
        message=(
            f"pytest not found via any strategy (tried: {tried}). "
            "Install pytest in the project venv or set judge command override."
        ),
        blocking=jd.blocking,
    )


async def _run_shell_judge(jd: JudgeDefinition, label: str, cwd: Path) -> JudgeResult:
    try:
        proc = await asyncio.create_subprocess_exec(
            *shlex.split(jd.target),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=jd.timeout_s)
        except TimeoutError:
            proc.kill()
            return JudgeResult(
                judge=label,
                type="shell",
                result="error",
                message=f"shell judge timed out after {jd.timeout_s}s: {jd.target}",
                blocking=jd.blocking,
            )
        passed = proc.returncode == 0
        err_hint = stderr.decode(errors="replace").strip()[-200:] if stderr else ""
        return JudgeResult(
            judge=label,
            type="shell",
            result="pass" if passed else "fail",
            message=(
                f"shell exit {proc.returncode} for {jd.target!r}"
                + (f": {err_hint}" if err_hint and not passed else "")
            ),
            blocking=jd.blocking,
        )
    except FileNotFoundError:
        return JudgeResult(
            judge=label,
            type="shell",
            result="error",
            message=f"shell command not found: {jd.target}",
            blocking=jd.blocking,
        )
    except Exception as exc:
        return JudgeResult(
            judge=label,
            type="shell",
            result="error",
            message=f"Unexpected error running shell judge: {exc}",
            blocking=jd.blocking,
        )


async def run_judges(
    definitions: list[dict[str, Any]],
    cwd: Path | None = None,
    *,
    changed_paths: list[str] | None = None,
    base_ref: str = "HEAD",
) -> dict[str, Any]:
    """Run a list of raw judge dicts and return aggregated results."""
    if not definitions:
        return {"judge_results": [], "judges_passed": True}

    work_dir = cwd or Path.cwd()
    effective_changed = changed_paths
    if effective_changed is None and any(d.get("when_changed") for d in definitions):
        effective_changed = _git_changed_paths(work_dir, base_ref)

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

    results = await asyncio.gather(
        *[run_judge(jd, work_dir, changed_paths=effective_changed) for jd in parsed]
    )

    any_blocking_fail = any(r.result in {"fail", "error"} and r.blocking for r in results)

    return {
        "judge_results": [r.model_dump() for r in results],
        "judges_passed": not any_blocking_fail,
    }
