"""Tests for scripts/ci_cost_guard.py — the $0 CI cost model gate.

TappsMCP is a public repository, so standard GitHub-hosted runners are free and
unmetered. The guard exists so that stays true by assertion rather than by
assumption: larger runners and runner groups are billed even on public repos.

See docs/adr/0035-ci-cost-model-and-scope.md.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    """Import scripts/ci_cost_guard.py — scripts/ is not an installed package."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import ci_cost_guard

    return ci_cost_guard


def _write_workflow(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(textwrap.dedent(body), encoding="utf-8")


class TestIsStandardRunner:
    """Only free-on-public standard runner labels are accepted."""

    @pytest.mark.parametrize(
        "label",
        [
            "ubuntu-latest",
            "ubuntu-24.04",
            "ubuntu-22.04",
            "ubuntu-24.04-arm",
            "windows-latest",
            "windows-2025",
            "macos-latest",
            "macos-15",
        ],
    )
    def test_standard_labels_accepted(self, guard: ModuleType, label: str) -> None:
        assert guard.is_standard_runner(label) is True

    @pytest.mark.parametrize(
        "label",
        [
            "ubuntu-latest-8-cores",
            "ubuntu-22.04-16core",
            "macos-latest-xlarge",
            "macos-13-large",
            "self-hosted",
            "group:big-runners",
            "buildjet-8vcpu-ubuntu-2204",
            "${{ matrix.unresolvable }}",
        ],
    )
    def test_billable_or_unknown_labels_rejected(self, guard: ModuleType, label: str) -> None:
        assert guard.is_standard_runner(label) is False


class TestFindBillableRunners:
    """The scan reports (workflow, job, label) for anything non-standard."""

    def test_clean_workflow_dir_has_no_offenders(self, guard: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "ok.yml",
            """
            name: ok
            on: [pull_request]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert guard.find_billable_runners(tmp_path) == []

    def test_larger_runner_is_reported(self, guard: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "pricey.yml",
            """
            name: pricey
            on: [pull_request]
            jobs:
              heavy:
                runs-on: ubuntu-latest-8-cores
                steps:
                  - run: echo hi
            """,
        )
        offenders = guard.find_billable_runners(tmp_path)
        assert offenders == [("pricey.yml", "heavy", "ubuntu-latest-8-cores")]

    def test_runner_group_is_reported(self, guard: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "grouped.yml",
            """
            name: grouped
            on: [pull_request]
            jobs:
              heavy:
                runs-on:
                  group: big-runners
                  labels: [ubuntu-latest]
                steps:
                  - run: echo hi
            """,
        )
        offenders = guard.find_billable_runners(tmp_path)
        assert ("grouped.yml", "heavy", "group:big-runners") in offenders

    def test_matrix_runner_is_expanded(self, guard: ModuleType, tmp_path: Path) -> None:
        """A matrix of runners is checked per value, not treated as opaque."""
        _write_workflow(
            tmp_path,
            "matrix.yml",
            """
            name: matrix
            on: [pull_request]
            jobs:
              build:
                strategy:
                  matrix:
                    os: [ubuntu-latest, macos-latest-xlarge]
                runs-on: ${{ matrix.os }}
                steps:
                  - run: echo hi
            """,
        )
        offenders = guard.find_billable_runners(tmp_path)
        assert offenders == [("matrix.yml", "build", "macos-latest-xlarge")]

    def test_reusable_workflow_job_without_runs_on_is_skipped(
        self, guard: ModuleType, tmp_path: Path
    ) -> None:
        _write_workflow(
            tmp_path,
            "caller.yml",
            """
            name: caller
            on: [pull_request]
            jobs:
              delegate:
                uses: ./.github/workflows/other.yml
            """,
        )
        assert guard.find_billable_runners(tmp_path) == []


class TestScheduledWorkflows:
    """`on:` parses as the boolean True under YAML 1.1 unless quoted."""

    def test_detects_schedule_trigger(self, guard: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "cron.yml",
            """
            name: cron
            on:
              schedule:
                - cron: "0 5 * * 1"
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert guard.count_scheduled_workflows(tmp_path) == ["cron.yml"]

    def test_ignores_unscheduled_workflow(self, guard: ModuleType, tmp_path: Path) -> None:
        _write_workflow(
            tmp_path,
            "pr.yml",
            """
            name: pr
            on:
              pull_request:
                branches: [master]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: echo hi
            """,
        )
        assert guard.count_scheduled_workflows(tmp_path) == []


class TestLiveRepository:
    """The guard's whole point: assert it against this repo's real workflows."""

    def test_no_billable_runners_in_this_repo(self, guard: ModuleType) -> None:
        offenders = guard.find_billable_runners()
        assert offenders == [], (
            "These jobs would be billed even on a public repository: "
            + ", ".join(f"{w}:{j} ({label})" for w, j, label in offenders)
        )

    def test_every_workflow_declares_at_least_one_job(self, guard: ModuleType) -> None:
        for path, workflow in guard.iter_workflows():
            assert workflow.get("jobs"), f"{path.name} declares no jobs"
