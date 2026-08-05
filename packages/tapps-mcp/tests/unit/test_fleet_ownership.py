"""Tests for fleet port ownership and release detection (TAP-5630).

A server from a previous release that survives a deploy keeps its port. The
replacement cannot bind, dies, and leaves its pidfile behind — and every
port-based check then reports healthy while the old release serves traffic.
These tests cover the helpers that make that visible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.distribution.fleet_ownership import (
    find_port_owner,
    process_release,
    read_process_cmdline,
)

RELEASE_BIN = "/home/u/.tapps-mcp/releases/3.12.65-6696aaf3/bin/python"
SERVE = "/home/u/.tapps-mcp/current/bin/tapps-mcp serve --profile nlt-build --transport http"


def _fake_proc(root: Path, pid: int, cmdline: str) -> None:
    """Write a /proc-shaped cmdline (NUL-separated argv) for *pid*."""
    entry = root / str(pid)
    entry.mkdir(parents=True)
    (entry / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode() + b"\0")


class TestReadProcessCmdline:
    def test_nul_separated_argv_becomes_a_string(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 42, "python serve --port 8760")
        assert read_process_cmdline(42, proc_root=tmp_path) == "python serve --port 8760"

    def test_missing_process_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert read_process_cmdline(9999, proc_root=tmp_path) == ""


class TestProcessRelease:
    def test_release_directory_is_extracted(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 1, f"{RELEASE_BIN} {SERVE} --port 8760")
        assert process_release(1, proc_root=tmp_path) == "3.12.65-6696aaf3"

    def test_an_older_release_is_reported_as_itself(self, tmp_path: Path) -> None:
        """The orphan case: the port answers, but from the previous release."""
        old = RELEASE_BIN.replace("3.12.65-6696aaf3", "3.12.64-0632ad3d")
        _fake_proc(tmp_path, 2, f"{old} {SERVE} --port 8760")
        assert process_release(2, proc_root=tmp_path) == "3.12.64-0632ad3d"

    def test_a_process_outside_a_release_tree_has_none(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 3, "/home/u/code/tapps-mcp/.venv/bin/python -m tapps_mcp serve")
        assert process_release(3, proc_root=tmp_path) is None

    def test_missing_process_has_none(self, tmp_path: Path) -> None:
        assert process_release(404, proc_root=tmp_path) is None


class TestFindPortOwner:
    def test_finds_the_fleet_serve_bound_to_the_port(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 100, f"{RELEASE_BIN} {SERVE} --port 8760")
        assert find_port_owner(8760, proc_root=tmp_path) == 100

    def test_equals_form_of_the_port_flag_also_matches(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 101, f"{RELEASE_BIN} {SERVE} --port=8761")
        assert find_port_owner(8761, proc_root=tmp_path) == 101

    def test_a_different_port_is_not_matched(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 102, f"{RELEASE_BIN} {SERVE} --port 8760")
        assert find_port_owner(8761, proc_root=tmp_path) is None

    def test_a_stdio_serve_is_not_a_fleet_owner(self, tmp_path: Path) -> None:
        _fake_proc(tmp_path, 103, "tapps-mcp serve --profile nlt-build --port 8760")
        assert find_port_owner(8760, proc_root=tmp_path) is None

    def test_an_unrelated_listener_is_never_matched(self, tmp_path: Path) -> None:
        """Only fleet serves may be reclaimed — never someone else's process."""
        _fake_proc(tmp_path, 104, "/usr/bin/nginx -g daemon off; --port 8760")
        assert find_port_owner(8760, proc_root=tmp_path) is None

    def test_non_numeric_proc_entries_are_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "self").mkdir()
        (tmp_path / "meminfo").write_text("x")
        _fake_proc(tmp_path, 105, f"{RELEASE_BIN} {SERVE} --port 8762")
        assert find_port_owner(8762, proc_root=tmp_path) == 105

    def test_absent_proc_filesystem_is_handled(self, tmp_path: Path) -> None:
        assert find_port_owner(8760, proc_root=tmp_path / "nope") is None


@pytest.mark.parametrize("port", [8760, 8761, 8762, 8763, 8764, 8765])
def test_every_fleet_port_can_be_resolved(tmp_path: Path, port: int) -> None:
    _fake_proc(tmp_path, 200 + port, f"{RELEASE_BIN} {SERVE} --port {port}")
    assert find_port_owner(port, proc_root=tmp_path) == 200 + port
