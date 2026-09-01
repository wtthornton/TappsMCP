"""TAP-6885: ``scripts/start-program.sh`` scaffolded via the executable asset class.

Covers the two things this lane ships: the script itself (placed by
``tapps_init``, refreshed by ``tapps_upgrade``, with a skip token) and its
behavior as a multi-session kickoff (refusals, worktree/partition creation,
idempotence).
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_skill_orchestration import (
    START_PROGRAM_SCRIPT_BODY,
    generate_start_program_script,
)
from tapps_mcp.pipeline.upgrade import _skipped
from tapps_mcp.pipeline.upgrade_skip_tokens import ALL_SKIP_TOKENS, SKIP_TOKENS


class TestGenerateStartProgramScript:
    def test_creates_executable_script_that_parses_as_bash(self, tmp_path: Path) -> None:
        result = generate_start_program_script(tmp_path)
        target = tmp_path / "scripts" / "start-program.sh"
        assert result == {"file": "scripts/start-program.sh", "action": "created"}
        assert target.exists()
        assert target.stat().st_mode & 0o111, "script must land executable"
        check = subprocess.run(
            ["bash", "-n", str(target)], capture_output=True, text=True, timeout=10
        )
        assert check.returncode == 0, check.stderr

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        result = generate_start_program_script(tmp_path, dry_run=True)
        assert result["action"] == "created"
        assert not (tmp_path / "scripts" / "start-program.sh").exists()

    def test_refresh_preserves_customization_outside_the_block(self, tmp_path: Path) -> None:
        generate_start_program_script(tmp_path)
        target = tmp_path / "scripts" / "start-program.sh"
        addendum = "\n# project note: billing account is acme-org\n"
        target.write_text(target.read_text(encoding="utf-8") + addendum, encoding="utf-8")

        result = generate_start_program_script(tmp_path)

        text = target.read_text(encoding="utf-8")
        assert result["action"] == "unchanged"
        assert text.endswith(addendum)
        check = subprocess.run(
            ["bash", "-n", str(target)], capture_output=True, text=True, timeout=10
        )
        assert check.returncode == 0, check.stderr

    def test_usage_does_not_self_reference_source_line_numbers(self) -> None:
        """Regression guard: the asset wrapper prepends 2 lines (policy header +

        BEGIN marker) ahead of the body, so a `sed -n '<N>,<M>p' "${BASH_SOURCE[0]}"``
        usage() would read the wrong lines once deployed. usage() must print a
        literal block instead.
        """
        assert (
            "BASH_SOURCE"
            not in START_PROGRAM_SCRIPT_BODY.split("usage() {")[1].split("}")[0].split("cat >&2")[0]
        )
        assert "cat >&2 <<'USAGE'" in START_PROGRAM_SCRIPT_BODY


class TestSkipTokenVocabulary:
    def test_token_key_is_the_internal_name_value_is_the_path(self) -> None:
        assert SKIP_TOKENS["start_program_script"] == frozenset({"scripts/start-program.sh"})

    def test_token_is_in_the_recognized_vocabulary(self) -> None:
        assert "scripts/start-program.sh" in ALL_SKIP_TOKENS

    def test_skipped_gates_on_the_path_value_not_the_key(self) -> None:
        assert _skipped("start_program_script", {"scripts/start-program.sh"}) is True
        assert _skipped("start_program_script", {"start_program_script"}) is False
        assert _skipped("start_program_script", set()) is False


@pytest.fixture
def program_repo(tmp_path: Path):
    """A throwaway git repo with a committed HEAD, so `git worktree add` works."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True)
    generate_start_program_script(repo)
    (repo / "prompts").mkdir()
    (repo / "prompts" / "driver.md").write_text("# driver prompt\n", encoding="utf-8")

    slug = f"t{uuid.uuid4().hex[:8]}"
    yield repo, slug

    for wt in Path("/tmp").glob(f"prog-{slug}-*"):
        shutil.rmtree(wt, ignore_errors=True)


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/start-program.sh", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestStartProgramScriptRefusals:
    """Evidence item 1: each refusal fails first (shown here), never silently passes."""

    def test_fewer_than_two_sessions_refuses(self, program_repo) -> None:
        repo, slug = program_repo
        result = _run(repo, slug, "prompts/driver.md", "solo", "solo")
        assert result.returncode == 2
        assert "need >=2 sessions" in result.stderr

    def test_integrator_absent_from_roster_refuses(self, program_repo) -> None:
        repo, slug = program_repo
        result = _run(repo, slug, "prompts/driver.md", "ghost", "a", "b")
        assert result.returncode == 2
        assert "not in the session list" in result.stderr

    def test_missing_driver_prompt_refuses(self, program_repo) -> None:
        repo, slug = program_repo
        result = _run(repo, slug, "prompts/does-not-exist.md", "a", "a", "b")
        assert result.returncode == 1
        assert "no such driver prompt" in result.stderr


class TestStartProgramScriptHappyPath:
    """Evidence items 2-3: real worktrees/partition/decisions/status, and idempotence."""

    def test_creates_worktrees_partition_decisions_and_status(self, program_repo) -> None:
        repo, slug = program_repo
        result = _run(repo, slug, "prompts/driver.md", "a", "a", "b")
        assert result.returncode == 0, result.stderr

        assert Path(f"/tmp/prog-{slug}-a").is_dir()
        assert Path(f"/tmp/prog-{slug}-b").is_dir()

        program_dir = repo / "reports" / "programs" / slug
        partition = (program_dir / "partition.md").read_text(encoding="utf-8")
        assert "Integrator (the only session that merges): **a**" in partition
        assert "`a`" in partition and "`b`" in partition

        decisions = (program_dir / "decisions.md").read_text(encoding="utf-8")
        assert "Dispatch pool / billing account" in decisions

        assert (program_dir / "status" / "a.md").exists()
        assert (program_dir / "status" / "b.md").exists()

    def test_rerun_reuses_worktrees_and_preserves_edited_decisions(self, program_repo) -> None:
        repo, slug = program_repo
        _run(repo, slug, "prompts/driver.md", "a", "a", "b")

        decisions_path = repo / "reports" / "programs" / slug / "decisions.md"
        edited = decisions_path.read_text(encoding="utf-8").replace(
            "| 1 | Dispatch pool / billing account | _fill in_ | ASK |",
            "| 1 | Dispatch pool / billing account | acme-org | PRE-AUTHORISED |",
        )
        decisions_path.write_text(edited, encoding="utf-8")

        result = _run(repo, slug, "prompts/driver.md", "a", "a", "b")

        assert result.returncode == 0, result.stderr
        assert "reusing" in result.stdout
        assert "acme-org" in decisions_path.read_text(encoding="utf-8")
