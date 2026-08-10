"""Tests for release-aware reaping of stranded fleet servers (TAP-5733 follow-up).

The predicate here is safety-critical: it is the one place allowed to kill a
shared HTTP fleet process, which ADR-0024 otherwise protects absolutely. Every
negative case below is a way this could take down a live fleet, so they matter
more than the positive one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.distribution.fleet_ownership import find_superseded_fleet_pids

CURRENT = "3.12.71-b9be914f"
OLD = "3.12.69-c69ef8a6"


def _fake_proc(root: Path, pid: int, cmdline: str) -> None:
    """Write a /proc-style cmdline (NUL-separated) for *pid*."""
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode("utf-8"))


def _fleet_cmd(release: str, profile: str, port: int) -> str:
    return (
        f"/home/u/.tapps-mcp/releases/{release}/bin/python "
        f"/home/u/.tapps-mcp/current/bin/tapps-mcp serve "
        f"--profile {profile} --transport http --host 127.0.0.1 --port {port}"
    )


@pytest.fixture
def proc_root(tmp_path: Path) -> Path:
    d = tmp_path / "proc"
    d.mkdir()
    return d


@pytest.fixture
def pid_dir(tmp_path: Path) -> Path:
    d = tmp_path / "pids"
    d.mkdir()
    return d


def _claim(pid_dir: Path, server_id: str, pid: int) -> None:
    (pid_dir / f"{server_id}.pid").write_text(str(pid), encoding="utf-8")


class TestFindsStrandedServers:
    def test_superseded_and_unclaimed_is_reported(self, proc_root: Path, pid_dir: Path) -> None:
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-build", 8760))
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == [100]

    def test_multiple_are_sorted(self, proc_root: Path, pid_dir: Path) -> None:
        _fake_proc(proc_root, 300, _fleet_cmd(OLD, "nlt-setup", 8762))
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-build", 8760))
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == [
            100,
            300,
        ]


class TestNeverTouchesLiveFleet:
    """Each of these would be an outage if the predicate got it wrong."""

    def test_current_release_is_left_alone(self, proc_root: Path, pid_dir: Path) -> None:
        _fake_proc(proc_root, 100, _fleet_cmd(CURRENT, "nlt-build", 8760))
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == []

    def test_pidfile_claimed_is_left_alone_even_if_superseded(
        self, proc_root: Path, pid_dir: Path
    ) -> None:
        """Mid-deploy: an old server still owns its port and is still claimed."""
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-build", 8760))
        _claim(pid_dir, "nlt-build", 100)
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == []

    def test_unknown_current_release_reaps_nothing(self, proc_root: Path, pid_dir: Path) -> None:
        """No `current` symlink — never guess and kill on incomplete info."""
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-build", 8760))
        assert find_superseded_fleet_pids(None, pid_dir=pid_dir, proc_root=proc_root) == []
        assert find_superseded_fleet_pids("", pid_dir=pid_dir, proc_root=proc_root) == []

    def test_stdio_server_is_not_fleet_and_is_left_alone(
        self, proc_root: Path, pid_dir: Path
    ) -> None:
        """ADR-0005 owns stdio reaping; this predicate must not poach it."""
        _fake_proc(
            proc_root,
            100,
            f"/home/u/.tapps-mcp/releases/{OLD}/bin/tapps-mcp serve --profile nlt-build",
        )
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == []

    def test_non_release_process_is_left_alone(self, proc_root: Path, pid_dir: Path) -> None:
        """An editable-checkout fleet run has no release dir to compare."""
        _fake_proc(
            proc_root,
            100,
            "/home/u/code/tapps-mcp/.venv/bin/tapps-mcp serve --profile nlt-build "
            "--transport http --port 8760",
        )
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == []

    def test_unrelated_process_is_left_alone(self, proc_root: Path, pid_dir: Path) -> None:
        _fake_proc(proc_root, 100, "/usr/bin/postgres -D /var/lib/postgresql/data")
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == []

    def test_transport_equals_form_is_recognised_as_fleet(
        self, proc_root: Path, pid_dir: Path
    ) -> None:
        """`--transport=http` must count as fleet, same as `--transport http`."""
        _fake_proc(
            proc_root,
            100,
            f"/home/u/.tapps-mcp/releases/{OLD}/bin/tapps-mcp serve "
            f"--profile nlt-build --transport=http --port 8760",
        )
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == [100]


class TestDegradedInputs:
    def test_missing_proc_root_returns_empty(self, tmp_path: Path, pid_dir: Path) -> None:
        assert (
            find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=tmp_path / "absent")
            == []
        )

    def test_missing_pid_dir_still_finds_strays(self, proc_root: Path, tmp_path: Path) -> None:
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-build", 8760))
        found = find_superseded_fleet_pids(
            CURRENT, pid_dir=tmp_path / "absent", proc_root=proc_root
        )
        assert found == [100]

    def test_unreadable_pidfile_does_not_abort_the_scan(
        self, proc_root: Path, pid_dir: Path
    ) -> None:
        (pid_dir / "nlt-build.pid").write_text("not-a-pid", encoding="utf-8")
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-memory", 8761))
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == [100]

    def test_non_numeric_proc_entries_are_skipped(self, proc_root: Path, pid_dir: Path) -> None:
        (proc_root / "self").mkdir()
        (proc_root / "meminfo").write_text("", encoding="utf-8")
        _fake_proc(proc_root, 100, _fleet_cmd(OLD, "nlt-build", 8760))
        assert find_superseded_fleet_pids(CURRENT, pid_dir=pid_dir, proc_root=proc_root) == [100]
