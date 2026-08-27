"""TAP-6068 acceptance item 4: the CLI ``validate-changed`` path behaves the
SAME as the MCP tool path — for the zero-file inconclusive case (round 2:
neither path mints an ok-marker) and the pre-existing-debt case (both mint)
— batch-at-gate lanes are not starved.

``cli_validation._run_validate_changed`` calls
``tapps_mcp.server_pipeline_tools.tapps_validate_changed`` directly (same
function, not a reimplementation), so marker parity holds by construction;
these tests exercise that end to end against a hermetic scratch repo rather
than just asserting the call graph.

Round 2 (TAP-6068 follow-up): the zero-file path previously minted the same
ok-marker a passing batch would. That was a validation token issued for
zero validation — a zero-file run in a project with an unvalidated,
gate-failing file could mint the marker and let the blocking Stop/
TaskCompleted hook pass. The mint is removed; ``TestZeroFileMarkerRegression``
below covers the non-git and git-root cases directly against the rendered
hook scripts.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from tapps_mcp.cli_validation import validate_changed_cmd
from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS_BLOCKING


def _init_scratch_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)


@pytest.fixture(autouse=True)
def _restore_cwd() -> Iterator[None]:
    """``validate_changed_cmd --project-root`` chdirs the process; restore it."""
    original = Path.cwd()
    yield
    os.chdir(original)


class TestCliMarkerParity:
    def test_cli_zero_files_does_not_write_marker(self, tmp_path: Path) -> None:
        """A zero-file run mints nothing on either path (round 2, TAP-6068).

        Minting an ok-marker for a run that validated zero files was a
        validation token issued for zero validation — it let a zero-file
        ``tapps_validate_changed`` call green-light the blocking hook ahead
        of an unvalidated, gate-failing file. ``inconclusive: True``
        (TAP-5734) still distinguishes "nothing was gated" from "checked
        and failed" for callers that read the field; it does not mint.
        """
        _init_scratch_repo(tmp_path)
        marker = tmp_path / ".tapps-mcp" / ".validation-marker"
        assert not marker.exists()

        runner = CliRunner()
        result = runner.invoke(validate_changed_cmd, ["--quick", "--project-root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert not marker.exists(), "CLI path must NOT mint an ok-marker for a zero-file run"

    def test_cli_pre_existing_debt_only_writes_marker(self, tmp_path: Path) -> None:
        """Same as the MCP path's zero-delta-debt case (TAP-6068 acceptance 3)."""
        debt_file = tmp_path / "debt.py"
        # Deterministically fails the standard gate (unused imports, unused
        # var, undefined name) — verified via ruff to score 68.4 < 70.
        debt_file.write_text(
            "import os\nimport sys\nimport json\n\n\n"
            "def f(x):\n"
            "    if x == 1:\n"
            "        if x == 1:\n"
            "            if x == 1:\n"
            "                if x == 1:\n"
            "                    return x\n"
            "    y = unused_var_typo\n"
            "    return None\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "add debt"], cwd=tmp_path, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=tmp_path, check=True)

        marker = tmp_path / ".tapps-mcp" / ".validation-marker"

        runner = CliRunner()
        result = runner.invoke(
            validate_changed_cmd,
            ["--quick", "--project-root", str(tmp_path), "--file-paths", str(debt_file)],
        )

        # debt.py is untouched since the trunk commit — zero-delta pre-existing
        # debt, and genuinely fails the gate (exit_code != 0 confirms the gate
        # verdict is real, not accidentally clean). TAP-6068 requires the
        # ok-marker to still be minted on a debt-only failure.
        assert result.exit_code != 0, result.output
        assert marker.exists(), "CLI path must mint the ok-marker on debt-only failures too"

    # NOTE: a direct in-process "call the MCP function, then invoke the CLI
    # command" comparison was deliberately NOT added here. tapps_core's
    # settings loader caches a process-wide singleton on the first bare
    # ``load_settings()`` call; calling the MCP path with an explicit
    # ``project_root=`` override still makes that first bare call internally
    # (before applying the override), which primes the cache with whatever
    # ``Path.cwd()`` was at that point — and a subsequent CLI invocation in
    # the SAME test then reads that stale cached root instead of the one its
    # own ``os.chdir`` just set. That is a same-process test artifact (a real
    # CLI process and a real MCP host are each a fresh process), not a
    # product bug — reproducing it here would validate against this repo's
    # own live working tree, which the hermetic-test policy explicitly
    # forbids. Parity is established instead by: (a) reading
    # ``cli_validation._run_validate_changed`` — it calls
    # ``tapps_mcp.server_pipeline_tools.tapps_validate_changed`` directly,
    # not a reimplementation; and (b) the two tests above, which exercise
    # that exact function through the CLI entry point in isolation.


@pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="bash required",
)
class TestZeroFileMarkerRegression:
    """Round 2 (TAP-6068 follow-up): the removed zero-file mint stays removed.

    A zero-file gate result is not proof that anything was validated — it
    must never green-light the blocking Stop/TaskCompleted hook on its own.
    The honest "clean session" pass comes from the hooks' own git-diff
    guard (no scorable changes in the tree), not from a marker minted by
    a zero-file tool call.
    """

    def test_zero_file_run_in_non_git_root_leaves_no_marker(self, tmp_path: Path) -> None:
        """A non-git project root has no diff to guard on at all — the
        zero-file run must still leave no marker rather than compensating
        by minting one."""
        marker = tmp_path / ".tapps-mcp" / ".validation-marker"
        assert not marker.exists()

        runner = CliRunner()
        result = runner.invoke(validate_changed_cmd, ["--quick", "--project-root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert not marker.exists(), "a non-git zero-file run must not mint an ok-marker"

    def test_zero_file_run_in_git_root_leaves_no_marker_and_hook_still_passes(
        self, tmp_path: Path
    ) -> None:
        """The honest case survives without the mint: a zero-file validate
        run writes no marker, and the rendered blocking hook still exits 0
        on the clean tree because its own git-diff guard finds no scorable
        changes — not because a marker was minted for it."""
        _init_scratch_repo(tmp_path)
        marker = tmp_path / ".tapps-mcp" / ".validation-marker"

        runner = CliRunner()
        result = runner.invoke(validate_changed_cmd, ["--quick", "--project-root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert not marker.exists(), "a git-root zero-file run must not mint an ok-marker"

        script_path = tmp_path / "tapps-task-completed.sh"
        script_path.write_text(
            CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-task-completed.sh"], encoding="utf-8"
        )
        proc = subprocess.run(
            ["bash", str(script_path)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=tmp_path,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        )
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
        assert "OK" in proc.stderr
