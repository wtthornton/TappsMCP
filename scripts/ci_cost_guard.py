#!/usr/bin/env python3
"""Keep this repo's GitHub Actions bill at $0 by construction.

TappsMCP is a **public** repository, and standard GitHub-hosted runners are free
and unmetered on public repos. That is the entire reason CI here costs nothing —
not the number of workflows, not the trigger filters, not the schedule count.
Two things can silently break it:

1. A workflow adopts a **larger runner** (``ubuntu-latest-8-cores``,
   ``macos-latest-xlarge``, a runner ``group:``). Larger runners are billed even
   on public repositories.
2. The repository is **flipped to private**, at which point every job becomes
   metered against the account's minute allotment.

This module checks (1) as a hard gate and reports (2) as a notice, so the cost
model is asserted in CI rather than assumed. See
``docs/adr/0035-ci-cost-model-and-scope.md``.

Usage:
    python3 scripts/ci_cost_guard.py
    python3 scripts/ci_cost_guard.py --visibility private

Exit codes:
    0 — every job runs on a standard (free-on-public) GitHub-hosted runner
    1 — a job uses a runner that is billable even on a public repository
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Standard GitHub-hosted runner labels. These are free and unmetered on public
# repositories. Anything outside this set is treated as billable — including
# `-xlarge` / `-Ncore` variants and self-hosted / runner-group targets.
_STANDARD_RUNNERS = (
    re.compile(r"^ubuntu-(latest|\d{2}\.\d{2})(-arm)?$"),
    re.compile(r"^windows-(latest|\d{4})(-arm)?$"),
    re.compile(r"^macos-(latest|\d{2})$"),
)

_MATRIX_REF = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}$")


def is_standard_runner(label: str) -> bool:
    """Return True if ``label`` is a standard runner (free on public repos)."""
    return any(pattern.match(label) for pattern in _STANDARD_RUNNERS)


def _runner_labels(runs_on: Any, matrix: dict[str, Any]) -> list[str]:
    """Normalise a ``runs-on`` value into the concrete labels it can resolve to.

    Handles the string, list, and ``{group:, labels:}`` mapping forms, and
    expands ``${{ matrix.foo }}`` against the job's own ``strategy.matrix``.
    """
    if isinstance(runs_on, dict):
        # A runner `group:` is never a standard hosted runner.
        labels = runs_on.get("labels", [])
        resolved = [f"group:{runs_on['group']}"] if "group" in runs_on else []
        if isinstance(labels, str):
            labels = [labels]
        return resolved + [str(label) for label in labels]

    if isinstance(runs_on, list):
        return [str(item) for item in runs_on]

    label = str(runs_on)
    ref = _MATRIX_REF.match(label)
    if ref:
        values = matrix.get(ref.group(1))
        if isinstance(values, list):
            return [str(value) for value in values]
        # Unresolvable expression — report verbatim so it fails loudly rather
        # than passing as an opaque string.
    return [label]


def iter_workflows(workflow_dir: Path = WORKFLOW_DIR) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Yield ``(path, parsed)`` for every workflow file, sorted by name."""
    paths = sorted(
        [*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")],
        key=lambda p: p.name,
    )
    for path in paths:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            yield path, parsed


def find_billable_runners(workflow_dir: Path = WORKFLOW_DIR) -> list[tuple[str, str, str]]:
    """Return ``(workflow, job, label)`` for every non-standard runner found."""
    offenders: list[tuple[str, str, str]] = []
    for path, workflow in iter_workflows(workflow_dir):
        jobs = workflow.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job_name, job in jobs.items():
            if not isinstance(job, dict) or "runs-on" not in job:
                continue
            strategy = job.get("strategy") or {}
            matrix = strategy.get("matrix") if isinstance(strategy, dict) else {}
            for label in _runner_labels(job["runs-on"], matrix or {}):
                if not is_standard_runner(label):
                    offenders.append((path.name, str(job_name), label))
    return offenders


def count_scheduled_workflows(workflow_dir: Path = WORKFLOW_DIR) -> list[str]:
    """Return the names of workflows carrying a ``schedule:`` trigger.

    Free on public repos; the classic silent drain once a repo goes private.
    """
    scheduled: list[str] = []
    for path, workflow in iter_workflows(workflow_dir):
        # `on:` parses as the boolean True under YAML 1.1 unless quoted.
        triggers = workflow.get("on", workflow.get(True))
        if isinstance(triggers, dict) and "schedule" in triggers:
            scheduled.append(path.name)
    return scheduled


def main() -> int:
    """Run the cost guard and report findings."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--visibility",
        choices=("public", "private"),
        help="Repository visibility; pass github.event.repository.private from CI.",
    )
    args = parser.parse_args()

    offenders = find_billable_runners()
    if offenders:
        print("FAIL: workflows use runners that are billable even on a public repo:\n")
        for workflow, job, label in offenders:
            print(f"  {workflow}  job '{job}'  runs-on: {label}")
        print(
            "\nStandard GitHub-hosted runners (ubuntu-latest, windows-latest, "
            "macos-latest, and pinned-version equivalents) are free and unmetered "
            "on public repositories. Larger runners and runner groups are not.\n"
            "See docs/adr/0035-ci-cost-model-and-scope.md."
        )
        return 1

    scheduled = count_scheduled_workflows()
    print(f"OK: all jobs run on standard GitHub-hosted runners ({len(scheduled)} scheduled).")

    if args.visibility == "private":
        print(
            "::warning::Repository is PRIVATE — Actions minutes are now metered "
            "against the account allotment, and the $0 cost model in "
            "docs/adr/0035-ci-cost-model-and-scope.md no longer holds. "
            f"Scheduled workflows now billing on a timer: {', '.join(scheduled) or 'none'}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
