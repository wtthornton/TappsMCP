"""The quality gate must apply one policy on both triggers (TAP-7817).

``.github/workflows/tapps-quality.yml`` runs ``validate-changed`` on both
``pull_request`` and ``push``. Until TAP-7817 the push path left
``BASELINE_REF`` empty, so the ratchet silently switched off and the absolute
threshold applied -- a PR could pass its own check and the identical job then
fail on push, on the same file, with no code change in between.

These tests assert on the *mechanism*, not on the YAML prose: the workflow's
own ``run:`` script is extracted, its ``${{ }}`` expressions are interpolated
the way GitHub interpolates them, and the script is executed against a real
throwaway git repository with ``uv`` stubbed out. What is asserted is the
``tapps-mcp validate-changed`` argv each trigger actually resolves to.
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tapps-quality.yml"
JOB = "quality"
CHANGED_FILE = "packages/demo/mod.py"

_EXPR = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")

_STUB_UV = """#!/usr/bin/env bash
{ printf '%s\\t' "$@"; printf '\\n'; } >> "$UV_CALL_LOG"
exit 0
"""


@dataclasses.dataclass(frozen=True)
class Resolved:
    """What one trigger actually resolved the gate invocation to."""

    trigger: str
    argv: list[str]
    repo: Path

    @property
    def baseline(self) -> str | None:
        """The ``--baseline-ref`` value as spelled, or ``None`` if not passed."""
        if "--baseline-ref" not in self.argv:
            return None
        return self.argv[self.argv.index("--baseline-ref") + 1]

    def baseline_commit(self) -> str:
        """The commit the baseline ref names -- spelling is not the point."""
        spelled = self.baseline
        if spelled is None:
            raise AssertionError(f"{self.trigger} passed no --baseline-ref: {self.argv!r}")
        return _git(self.repo, "rev-parse", f"{spelled}^{{commit}}")

    def flag(self, name: str) -> str | None:
        if name not in self.argv:
            return None
        return self.argv[self.argv.index(name) + 1]


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One change, run through both triggers."""

    previous_master_commit: str
    change_commit: str
    pull_request: Resolved
    push: Resolved

    @property
    def both(self) -> tuple[Resolved, Resolved]:
        return (self.pull_request, self.push)


def _gate_step() -> dict[str, Any]:
    """The single ``run:`` step of the quality job, straight from the workflow."""
    if not WORKFLOW.is_file():
        raise AssertionError(f"workflow not found at {WORKFLOW}")
    doc = cast("dict[str, Any]", yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))
    steps = doc["jobs"][JOB]["steps"]
    runs = [s for s in steps if "run" in s and "validate-changed" in s["run"]]
    if len(runs) != 1:
        raise AssertionError(f"expected exactly 1 validate-changed step, found {len(runs)}")
    return cast("dict[str, Any]", runs[0])


def _interpolate(text: str, context: dict[str, str]) -> str:
    """Substitute ``${{ github.x }}`` the way GitHub does -- literal text.

    An expression the caller has no value for is a hard error: a workflow that
    grows a new expression must not silently interpolate to an empty string and
    leave these tests passing on a script GitHub would never run.
    """

    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise AssertionError(f"workflow uses unmapped expression ${{{{ {key} }}}}")
        return context[key]

    return _EXPR.sub(sub, text)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _build_origin(tmp_path: Path) -> tuple[Path, Path, str, str]:
    """A bare origin with master at C1 and a feature branch at C2.

    C2 edits the file C1 created, so the change is an ordinary modification --
    the case the ratchet grandfathers, and the case the two triggers disagreed
    about. Returns ``(origin, seed_clone, c1, c2)``.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=master", str(origin)],
        check=True,
        capture_output=True,
    )

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=master")
    _git(seed, "config", "user.email", "ci@example.invalid")
    _git(seed, "config", "user.name", "CI")
    _git(seed, "remote", "add", "origin", str(origin))

    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "C0")

    target = seed / CHANGED_FILE
    target.parent.mkdir(parents=True)
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(seed, "add", CHANGED_FILE)
    _git(seed, "commit", "-m", "C1")
    _git(seed, "push", "origin", "master")
    c1 = _git(seed, "rev-parse", "HEAD")

    _git(seed, "checkout", "-b", "feature")
    target.write_text("def f():\n    return 2\n", encoding="utf-8")
    _git(seed, "add", CHANGED_FILE)
    _git(seed, "commit", "-m", "C2")
    _git(seed, "push", "origin", "feature")
    c2 = _git(seed, "rev-parse", "HEAD")

    return origin, seed, c1, c2


def _run_gate_step(
    tmp_path: Path, origin: Path, checkout_at: str, context: dict[str, str]
) -> Resolved:
    """Run the workflow's gate step for one trigger and capture what it ran."""
    trigger = context["github.event_name"]
    work = tmp_path / f"work-{trigger}"
    subprocess.run(
        ["git", "clone", "--no-single-branch", str(origin), str(work)],
        check=True,
        capture_output=True,
    )
    _git(work, "config", "user.email", "ci@example.invalid")
    _git(work, "config", "user.name", "CI")
    _git(work, "checkout", "--detach", checkout_at)

    bindir = tmp_path / f"bin-{trigger}"
    bindir.mkdir()
    stub = bindir / "uv"
    stub.write_text(_STUB_UV, encoding="utf-8")
    stub.chmod(0o755)

    log = tmp_path / f"uv-calls-{trigger}.tsv"
    step = _gate_step()
    full_context = {**context, "github.workspace": str(work)}
    script_path = tmp_path / f"step-{trigger}.sh"
    script_path.write_text(_interpolate(step["run"], full_context), encoding="utf-8")

    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "UV_CALL_LOG": str(log),
    }
    for key, raw in (step.get("env") or {}).items():
        env[key] = _interpolate(str(raw), full_context)

    proc = subprocess.run(
        ["bash", str(script_path)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"gate step failed:\n{proc.stdout}\n{proc.stderr}"

    calls = (
        [
            line.rstrip("\t").split("\t")
            for line in log.read_text(encoding="utf-8").splitlines()
            if line
        ]
        if log.exists()
        else []
    )
    matches = [c for c in calls if "validate-changed" in c]
    assert len(matches) == 1, f"{trigger}: expected one validate-changed call, got {matches!r}"
    return Resolved(trigger=trigger, argv=matches[0], repo=work)


@pytest.fixture
def scenario(tmp_path: Path) -> Scenario:
    """The resolved gate invocation for each trigger, for one identical change.

    The PR runs first, while ``origin/master`` is still C1. The push then
    fast-forwards ``master`` to C2 -- which is what makes the bug reachable:
    by the time the push job runs, ``origin/master`` IS the pushed commit, so
    there is no branch tip left to ratchet against.
    """
    origin, seed, c1, c2 = _build_origin(tmp_path)

    pull_request = _run_gate_step(
        tmp_path,
        origin,
        c2,
        {
            "github.event_name": "pull_request",
            "github.base_ref": "master",
            "github.sha": c2,
            "github.event.before": "",
        },
    )

    _git(seed, "push", "origin", "feature:master")

    push = _run_gate_step(
        tmp_path,
        origin,
        c2,
        {
            "github.event_name": "push",
            "github.base_ref": "",
            "github.sha": c2,
            "github.event.before": c1,
        },
    )

    return Scenario(
        previous_master_commit=c1,
        change_commit=c2,
        pull_request=pull_request,
        push=push,
    )


def test_both_triggers_validate_the_same_file(scenario: Scenario) -> None:
    """Sanity: the control is not vacuous -- both triggers see the same change."""
    for resolved in scenario.both:
        assert resolved.flag("--file-paths") == CHANGED_FILE, resolved.trigger
        assert "--quick" in resolved.argv, resolved.trigger


def test_push_path_passes_a_ratchet_baseline(scenario: Scenario) -> None:
    """The push trigger must ratchet, not fall back to the absolute threshold."""
    assert scenario.push.baseline is not None, (
        "push path resolved to a validate-changed call with no --baseline-ref: "
        f"{scenario.push.argv!r} -- the ratchet is off and the absolute threshold applies"
    )


def test_both_triggers_resolve_the_same_baseline_commit(scenario: Scenario) -> None:
    """Same change, same baseline commit -- so the two verdicts cannot disagree.

    The refs are spelled differently by design (``origin/master`` on a PR, the
    pushed-from sha on a push); what must match is the commit they name.
    """
    push_base = scenario.push.baseline_commit()
    pr_base = scenario.pull_request.baseline_commit()

    assert push_base == scenario.previous_master_commit, (
        "push must ratchet against the previous commit on master, "
        f"got {push_base} want {scenario.previous_master_commit}"
    )
    assert pr_base == push_base, (
        f"the two triggers ratchet against different commits: "
        f"pull_request={pr_base} push={push_base}"
    )


def test_gate_invocations_are_identical_modulo_baseline_spelling(scenario: Scenario) -> None:
    """One policy, one command: the argvs differ only in how the ref is spelled."""
    normalised: list[list[str]] = []
    for resolved in scenario.both:
        argv = list(resolved.argv)
        argv[argv.index("--baseline-ref") + 1] = resolved.baseline_commit()
        normalised.append(argv)

    assert normalised[0] == normalised[1]
