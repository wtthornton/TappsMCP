"""Functional behavior tests for the scaffolded ``scripts/gitfacts.sh`` (TAP-6884).

Runs the file exactly as scaffolded by ``generate_gitfacts_script`` (managed-block
header + markers included) via subprocess with an explicit interpreter —
``bash scripts/gitfacts.sh ...`` — for the same reason documented on
:mod:`tapps_mcp.pipeline.platform_project_scripts`: the managed-block header and
BEGIN marker land ahead of the body's own ``#!`` shebang, so ``./scripts/gitfacts.sh``
direct execution is a known, out-of-scope limitation of the shipped asset class.

Every repo used here is local-only (a bare ``origin.git`` plus a clone), no
network access — ``gitfacts.sh`` hardcodes ``origin/main``, so every planted
repo uses ``main`` as its branch name to match.

Covers evidence-bar items:

4. ``landed`` distinguishes a fully superseded ref (identical file content
   already on origin/main, via a simulated squash-merge) from one that
   differs (unmerged work), on a planted example of each.
5. ``stale`` reports ``--assume-unchanged`` files — proven with a planted one,
   and proven that ``git status`` cannot see it (the reason the subcommand
   exists at all).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tapps_mcp.pipeline.platform_project_scripts import GITFACTS_SH_REL_PATH
from tapps_mcp.pipeline.platform_project_scripts import (
    generate_gitfacts_script as _generate_gitfacts_script,
)


def _scaffold(tmp_path: Path) -> Path:
    """Install the scaffolded gitfacts.sh under tmp_path and return its path."""
    _generate_gitfacts_script(tmp_path)
    return tmp_path / GITFACTS_SH_REL_PATH


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30, check=True
    )
    return result


def _run_gitfacts(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, timeout=30)


def _make_repo_with_origin(tmp_path: Path) -> Path:
    """A bare ``origin.git`` plus a ``work`` clone, both on branch ``main``,
    with ``work``'s ``origin/main`` remote-tracking ref fetched — the minimum
    fixture gitfacts.sh's hardcoded ``origin/main`` assumption needs."""
    remote = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(remote)],
        check=True,
        timeout=30,
    )
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, timeout=30)
    _git(work, "checkout", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@t.com")
    _git(work, "config", "user.name", "t")
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "remote", "set-branches", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    return work


class TestEvidenceItem4LandedDistinguishesSupersededFromDiffers:
    def test_fully_superseded_ref_is_named_as_such(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        work = _make_repo_with_origin(tmp_path)

        # Branch that adds feature.txt, never merged directly...
        _git(work, "checkout", "-q", "-b", "squashed-away")
        (work / "feature.txt").write_text("hello feature\n", encoding="utf-8")
        _git(work, "add", ".")
        _git(work, "commit", "-q", "-m", "add feature")
        _git(work, "checkout", "-q", "main")

        # ...but the identical content lands on main via a separate commit,
        # simulating a squash-merge.
        (work / "feature.txt").write_text("hello feature\n", encoding="utf-8")
        _git(work, "add", ".")
        _git(work, "commit", "-q", "-m", "squash-merged feature")
        _git(work, "push", "-q", "origin", "main")
        _git(work, "fetch", "-q", "origin")

        result = _run_gitfacts(script, "landed", str(work), "squashed-away")

        assert result.returncode == 0, result.stderr
        assert "identical on main : feature.txt" in result.stdout
        assert "VERDICT: all 1 file(s) already on origin/main -- ref is SUPERSEDED." in (
            result.stdout
        )

    def test_ref_that_genuinely_differs_is_named_as_such(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        work = _make_repo_with_origin(tmp_path)

        _git(work, "checkout", "-q", "-b", "unmerged-work")
        (work / "other.txt").write_text("still pending\n", encoding="utf-8")
        _git(work, "add", ".")
        _git(work, "commit", "-q", "-m", "pending work")

        result = _run_gitfacts(script, "landed", str(work), "unmerged-work")

        assert result.returncode == 0, result.stderr
        assert "DIFFERS or absent : other.txt" in result.stdout
        assert "VERDICT: 1 of 1 file(s) differ from origin/main." in result.stdout
        assert "Do NOT assume this is unmerged work." in result.stdout

    def test_ref_with_no_changes_at_all_is_the_trivial_case(self, tmp_path: Path) -> None:
        """Negative control distinct from both planted examples: a ref that adds
        nothing takes neither the superseded nor the differs branch."""
        script = _scaffold(tmp_path)
        work = _make_repo_with_origin(tmp_path)
        _git(work, "checkout", "-q", "-b", "no-op-branch")

        result = _run_gitfacts(script, "landed", str(work), "no-op-branch")

        assert result.returncode == 0, result.stderr
        assert "VERDICT: ref adds nothing vs origin/main" in result.stdout


class TestEvidenceItem5StaleReportsAssumeUnchangedFiles:
    def test_assume_unchanged_file_is_reported_and_git_status_is_blind_to_it(
        self, tmp_path: Path
    ) -> None:
        script = _scaffold(tmp_path)
        work = _make_repo_with_origin(tmp_path)

        (work / "README.md").write_text("modified but hidden\n", encoding="utf-8")
        _git(work, "update-index", "--assume-unchanged", "README.md")

        status = _git(work, "status", "--porcelain")
        assert status.stdout.strip() == "", (
            f"fixture invalid: git status should be blind to the assume-unchanged "
            f"modification, but reported:\n{status.stdout}"
        )

        result = _run_gitfacts(script, "stale", str(work))

        assert result.returncode == 0, result.stderr
        assert "ASSUME-UNCHANGED FILES PRESENT -- 'git status' is blind to these:" in (
            result.stdout
        )
        assert "README.md" in result.stdout

    def test_no_assume_unchanged_files_prints_no_warning(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        work = _make_repo_with_origin(tmp_path)

        result = _run_gitfacts(script, "stale", str(work))

        assert result.returncode == 0, result.stderr
        assert "ASSUME-UNCHANGED FILES PRESENT" not in result.stdout
        assert "VERDICT: current." in result.stdout
