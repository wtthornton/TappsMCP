"""TAP-6068 acceptance item 4: the CLI ``validate-changed`` path mints the
SAME ok-marker the MCP tool path does, for both the zero-file inconclusive
case and the pre-existing-debt case — batch-at-gate lanes are not starved.

``cli_validation._run_validate_changed`` calls
``tapps_mcp.server_pipeline_tools.tapps_validate_changed`` directly (same
function, not a reimplementation), so marker parity holds by construction;
these tests exercise that end to end against a hermetic scratch repo rather
than just asserting the call graph.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from tapps_mcp.cli_validation import validate_changed_cmd


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
    def test_cli_zero_files_writes_marker(self, tmp_path: Path) -> None:
        """Same as the MCP path's inconclusive-but-clean case (TAP-5734/6068)."""
        _init_scratch_repo(tmp_path)
        marker = tmp_path / ".tapps-mcp" / ".validation-marker"
        assert not marker.exists()

        runner = CliRunner()
        result = runner.invoke(validate_changed_cmd, ["--quick", "--project-root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert marker.exists(), "CLI path must mint the same ok-marker as the MCP path"

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
