"""TAP-7225: CLI repair of a worktree's ``.mcp.json`` root header.

``resolve_http_project_root_header`` bakes a literal absolute path at
generation time (TAP-2199 spike: ``${CLAUDE_PROJECT_DIR}`` reaches the server
unexpanded under ``claude -p``), so a linked worktree inheriting the
primary checkout's ``.mcp.json`` carries the wrong root. These tests prove
the ``tapps-mcp fleet repair-root --project-root <root>`` subcommand fixes
that for an arbitrary root, refuses a non-git root, and that the TAP-2199
guard against ``${...}`` placeholders still rejects every other unexpanded
template.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tapps_mcp.cli_fleet import fleet_group
from tapps_mcp.distribution.nlt_http_fleet import (
    build_nlt_http_mcp_entry,
    describe_http_fleet_entry_problem,
    is_valid_http_fleet_mcp_entry,
)


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)


def _write_mcp_json(root: Path, header_root: str) -> Path:
    path = root / ".mcp.json"
    entry = build_nlt_http_mcp_entry("nlt-build", project_root=Path(header_root), host="claude-code")
    path.write_text(json.dumps({"mcpServers": {"nlt-build": entry}}, indent=2) + "\n", encoding="utf-8")
    return path


def test_repair_root_rewrites_header_to_the_given_root(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    _git_init(worktree)
    mcp_json = _write_mcp_json(worktree, str(primary))

    before = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert before["mcpServers"]["nlt-build"]["headers"]["X-Tapps-Project-Root"] == str(primary)

    runner = CliRunner()
    result = runner.invoke(fleet_group, ["repair-root", "--project-root", str(worktree)])
    assert result.exit_code == 0, result.output

    after = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert after["mcpServers"]["nlt-build"]["headers"]["X-Tapps-Project-Root"] == str(worktree.resolve())


def test_repair_root_refuses_non_git_root(tmp_path: Path) -> None:
    scratch = tmp_path / "not-a-repo"
    scratch.mkdir()
    _write_mcp_json(scratch, str(tmp_path / "elsewhere"))

    runner = CliRunner()
    result = runner.invoke(fleet_group, ["repair-root", "--project-root", str(scratch)])
    assert result.exit_code != 0
    assert "not a git work tree" in result.output


def test_repair_root_leaves_other_servers_byte_identical(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    _git_init(worktree)
    mcp_json = worktree / ".mcp.json"
    other_entry = {"command": "some-other-mcp", "args": ["--flag"]}
    nlt_entry = build_nlt_http_mcp_entry(
        "nlt-build", project_root=Path("/wrong/root"), host="claude-code"
    )
    mcp_json.write_text(
        json.dumps({"mcpServers": {"nlt-build": nlt_entry, "other-server": other_entry}}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(fleet_group, ["repair-root", "--project-root", str(worktree)])
    assert result.exit_code == 0, result.output

    after = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert after["mcpServers"]["other-server"] == other_entry


@pytest.mark.parametrize("placeholder", ["${CLAUDE_PROJECT_DIR}", "${OTHER_VAR}"])
def test_tap_2199_guard_still_rejects_unexpanded_templates(placeholder: str) -> None:
    entry = build_nlt_http_mcp_entry("nlt-build", project_root=Path("/tmp/x"), host="claude-code")
    entry["headers"]["X-Tapps-Project-Root"] = placeholder
    assert is_valid_http_fleet_mcp_entry(entry) is False
    assert "unexpanded template" in describe_http_fleet_entry_problem(entry)
