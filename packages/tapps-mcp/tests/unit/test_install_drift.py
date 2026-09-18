"""Tests for TAP-2129 install-drift diagnostic and TAP-2200 upgrade drift gate.

Covers the three branches:

1. **Matched** — global binary version == source version → ``drifted=False`` per entry, ``drift_detected=False``.
2. **Drifted** — global binary version != source version → ``drifted=True``, ``drift_detected=True``, remediation hint populated.
3. **No global install** — ``shutil.which`` returns ``None`` → entry omitted; check silently skipped.

Also covers the ``doctor.check_docsmcp_binary_version_mismatch`` helper and the
TAP-2200 ``upgrade_pipeline`` drift gate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.common.models import InstallDriftDiagnostic, InstallDriftEntry
from tapps_mcp.diagnostics import (
    check_install_drift,
    format_upgrade_blocked_by_drift,
)
from tapps_mcp.distribution.doctor import (
    check_binary_version_mismatch,
    check_docsmcp_binary_version_mismatch,
)


def _mock_completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["mock"], returncode=returncode, stdout=stdout, stderr=""
    )


_REAL_SUBPROCESS_RUN = subprocess.run


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _build_fixture_repo(base_dir: Path, *, unmerged: bool) -> Path:
    """Build a real, throwaway git repo simulating a local install source (TAP-7847).

    A fake ``refs/remotes/origin/master`` is written directly (no network) pointing at
    the base commit. When ``unmerged``, a lane branch is checked out with one more
    commit that is never merged into that ref — reproducing the host condition
    (a global CLI built from a worktree whose HEAD is not contained in origin/master).
    """
    repo = base_dir / "src"
    repo.mkdir()
    _run_git(["init", "-b", "master"], repo)
    _run_git(["config", "user.email", "fixture@example.com"], repo)
    _run_git(["config", "user.name", "Fixture"], repo)
    (repo / "f.txt").write_text("1", encoding="utf-8")
    _run_git(["add", "."], repo)
    _run_git(["commit", "-m", "base"], repo)
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    _run_git(["update-ref", "refs/remotes/origin/master", base_sha], repo)
    _run_git(["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master"], repo)
    if unmerged:
        _run_git(["checkout", "-b", "lane/scratch-fixture"], repo)
        (repo / "f.txt").write_text("2", encoding="utf-8")
        _run_git(["commit", "-am", "lane change"], repo)
    return repo


def _build_local_install_fixture(tmp_path: Path, repo_dir: Path) -> Path:
    """Write a fake uv-tool receipt pointing the CLI's install source at *repo_dir*."""
    receipt_dir = tmp_path / "uv-tool" / "tapps-mcp"
    bin_dir = receipt_dir / "bin"
    bin_dir.mkdir(parents=True)
    fake_bin = bin_dir / "tapps-mcp"
    fake_bin.write_text("", encoding="utf-8")  # never executed — subprocess.run is dispatched below
    (receipt_dir / "uv-receipt.toml").write_text(f'source = "{repo_dir}"\n', encoding="utf-8")
    return fake_bin


def _dispatch_git_or_version(version: str):  # type: ignore[no-untyped-def]
    """subprocess.run side_effect: real git for ``git ...``, a fake ``--version`` reply otherwise."""

    def _run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if cmd and cmd[0] == "git":
            return _REAL_SUBPROCESS_RUN(cmd, **kwargs)
        return _mock_completed(f"tapps-mcp, version {version}")

    return _run


@pytest.fixture(autouse=True)
def _disable_blue_green_binary_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests mock PATH/global installs; isolate from live ~/.tapps-mcp/current."""
    monkeypatch.setattr(
        "tapps_mcp.distribution.blue_green.resolve_blue_green_binary",
        lambda _name: None,
    )


class TestCheckInstallDriftMatched:
    """Branch 1: both binaries on PATH at the same version as the source."""

    def test_returns_diagnostic_with_no_drift(self) -> None:
        from docs_mcp import __version__ as docs_v
        from tapps_mcp import __version__ as tapps_v

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: f"/fake/{name}"
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    _mock_completed(f"tapps-mcp, version {tapps_v}"),
                    _mock_completed(f"docsmcp, version {docs_v}"),
                ]
                result = check_install_drift()

        assert isinstance(result, InstallDriftDiagnostic)
        assert result.drift_detected is False
        assert result.remediation_hint == ""
        assert len(result.entries) == 2
        assert all(not e.drifted for e in result.entries)


class TestCheckInstallDriftDrifted:
    """Branch 2: at least one binary drifts."""

    def test_remediation_hint_populated(self) -> None:
        from tapps_mcp import __version__ as tapps_v

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: f"/fake/{name}" if name == "tapps-mcp" else None
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.return_value = _mock_completed("tapps-mcp, version 99.0.0")
                result = check_install_drift()

        assert result.drift_detected is True
        assert "Reload MCP" in result.remediation_hint
        assert "Run tapps-mcp deploy-local" not in result.remediation_hint
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.binary == "tapps-mcp"
        assert entry.binary_version == "99.0.0"
        assert entry.source_version == tapps_v
        assert entry.drifted is True

    def test_process_ahead_when_global_binary_older(self) -> None:
        from tapps_mcp import __version__ as tapps_v

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: f"/fake/{name}" if name == "tapps-mcp" else None
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.return_value = _mock_completed("tapps-mcp, version 0.0.1")
                result = check_install_drift()

        assert result.drift_detected is True
        assert "Reinstall" in result.remediation_hint or "deploy-local" in result.remediation_hint

    def test_only_drifted_binaries_trigger_flag(self) -> None:
        """Mixed state: one matched, one drifted → drift_detected stays True."""
        from docs_mcp import __version__ as docs_v
        from tapps_mcp import __version__ as tapps_v

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: f"/fake/{name}"
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    _mock_completed(f"tapps-mcp, version {tapps_v}"),
                    _mock_completed("docsmcp, version 0.1.0"),
                ]
                result = check_install_drift()

        assert result.drift_detected is True
        by_name = {e.binary: e for e in result.entries}
        assert by_name["tapps-mcp"].drifted is False
        assert by_name["docsmcp"].drifted is True
        assert by_name["docsmcp"].source_version == docs_v


class TestCheckInstallDriftNoGlobal:
    """Branch 3: nothing on PATH — silently skipped."""

    def test_empty_entries_when_no_binary_found(self) -> None:
        with patch("tapps_mcp.diagnostics.shutil.which", return_value=None):
            result = check_install_drift()

        assert result.drift_detected is False
        assert result.entries == []
        assert result.remediation_hint == ""

    def test_never_raises_on_subprocess_failure(self) -> None:
        """Timeouts / non-zero exits collapse to empty entry, not exceptions."""
        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: f"/fake/{name}" if name == "tapps-mcp" else None
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd=["x"], timeout=5)
                result = check_install_drift()

        assert result.drift_detected is False
        # The entry is recorded with empty binary_version so the operator can
        # tell the probe was attempted but failed; drifted stays False.
        assert len(result.entries) == 1
        assert result.entries[0].binary_version == ""
        assert result.entries[0].drifted is False


class TestCheckInstallDriftLocalSource:
    """TAP-4099: warn when global CLIs were installed from a local checkout."""

    def test_local_install_sets_warning_without_version_drift(self, tmp_path: Path) -> None:
        from tapps_mcp import __version__ as tapps_v

        receipt_dir = tmp_path / "uv-tool" / "tapps-mcp"
        receipt_dir.mkdir(parents=True)
        local_pkg = tmp_path / "packages" / "tapps-mcp"
        local_pkg.mkdir(parents=True)
        receipt = receipt_dir / "uv-receipt.toml"
        receipt.write_text(f'source = "{local_pkg}"\n', encoding="utf-8")
        fake_bin = receipt_dir / "bin" / "tapps-mcp"
        fake_bin.parent.mkdir(parents=True)
        fake_bin.write_text("", encoding="utf-8")

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: str(fake_bin) if name == "tapps-mcp" else None
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.return_value = _mock_completed(f"tapps-mcp, version {tapps_v}")
                result = check_install_drift()

        assert result.drift_detected is False
        assert result.local_install_warning is True
        assert result.entries[0].from_local_source is True
        assert "local checkout" in result.remediation_hint


class TestCheckInstallDriftBuildIdentity:
    """TAP-7847: two builds at the same version string can still differ in content.

    Reproduces the measured host condition with a scratch fixture worktree (never
    the operator's real global install): a local uv-tool install whose source is a
    git checkout on a branch not contained in origin/master.
    """

    def test_unmerged_worktree_reports_drift_despite_matching_version(self, tmp_path: Path) -> None:
        from tapps_mcp import __version__ as tapps_v

        repo = _build_fixture_repo(tmp_path, unmerged=True)
        fake_bin = _build_local_install_fixture(tmp_path, repo)

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: str(fake_bin) if name == "tapps-mcp" else None
            with patch(
                "tapps_mcp.diagnostics.subprocess.run",
                side_effect=_dispatch_git_or_version(tapps_v),
            ):
                result = check_install_drift()

        entry = next(e for e in result.entries if e.binary == "tapps-mcp")
        assert entry.binary_version == tapps_v
        assert entry.source_version == tapps_v
        assert entry.drifted is True, (
            "identical version string but unmerged worktree HEAD must still drift"
        )
        assert entry.install_branch == "lane/scratch-fixture"
        assert entry.install_head_contained_in_default is False
        assert result.drift_detected is True
        assert "lane/scratch-fixture" in result.remediation_hint
        assert str(repo) in result.remediation_hint

    def test_default_branch_worktree_reports_no_drift(self, tmp_path: Path) -> None:
        """Positive control: a merged (default-branch) worktree at a matching
        version must still report no drift after the fix — the check discriminates,
        it does not just always report drift."""
        from tapps_mcp import __version__ as tapps_v

        repo = _build_fixture_repo(tmp_path, unmerged=False)
        fake_bin = _build_local_install_fixture(tmp_path, repo)

        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: str(fake_bin) if name == "tapps-mcp" else None
            with patch(
                "tapps_mcp.diagnostics.subprocess.run",
                side_effect=_dispatch_git_or_version(tapps_v),
            ):
                result = check_install_drift()

        entry = next(e for e in result.entries if e.binary == "tapps-mcp")
        assert entry.install_head_contained_in_default is True
        assert entry.drifted is False
        assert result.drift_detected is False


class TestEntryShape:
    """InstallDriftEntry contract used by session_start consumers."""

    def test_all_fields_present_on_drift(self) -> None:
        with patch("tapps_mcp.diagnostics.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: "/fake/tapps-mcp" if name == "tapps-mcp" else None
            with patch("tapps_mcp.diagnostics.subprocess.run") as mock_run:
                mock_run.return_value = _mock_completed("tapps-mcp, version 0.0.1")
                result = check_install_drift()

        entry = result.entries[0]
        assert isinstance(entry, InstallDriftEntry)
        assert entry.binary == "tapps-mcp"
        assert entry.binary_path == "/fake/tapps-mcp"
        assert entry.binary_version == "0.0.1"
        assert entry.source_version != ""
        assert entry.drifted is True


class TestDoctorChecks:
    """Doctor-side check parity with the diagnostics path."""

    def test_tapps_mcp_check_skips_when_absent(self) -> None:
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None):
            result = check_binary_version_mismatch()
        assert result.ok is True
        assert "skipped" in result.message

    def test_docsmcp_check_skips_when_absent(self) -> None:
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None):
            result = check_docsmcp_binary_version_mismatch()
        assert result.ok is True
        assert "skipped" in result.message
        assert result.name == "docsmcp binary version"

    def test_docsmcp_check_reports_modern_remediation(self) -> None:
        # doctor.py does `import subprocess` lazily inside the helper, so we
        # patch the module-level subprocess.run rather than the doctor module's
        # attribute (which doesn't exist at module scope).
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value="/fake/docsmcp"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = _mock_completed("docsmcp, version 0.0.1")
                result = check_docsmcp_binary_version_mismatch()
        assert result.ok is False
        assert "uv tool install -e --reinstall" in result.detail
        assert "packages/docs-mcp" in result.detail


# ---------------------------------------------------------------------------
# TAP-2200: upgrade_pipeline drift gate
# ---------------------------------------------------------------------------


def _drifted_diagnostic() -> InstallDriftDiagnostic:
    """Return a fake drift diagnostic with docsmcp lagging."""
    from tapps_mcp import __version__

    return InstallDriftDiagnostic(
        drift_detected=True,
        entries=[
            InstallDriftEntry(
                binary="docsmcp",
                binary_path="/fake/docsmcp",
                binary_version="0.0.1",
                source_version=__version__,
                drifted=True,
            )
        ],
        remediation_hint=(
            "Refresh global tools: uv tool install -e --reinstall"
            " <path>/packages/tapps-mcp (and the same for packages/docs-mcp)"
        ),
    )


class TestUpgradePipelineDriftGate:
    """TAP-2200: upgrade_pipeline blocks on detected install drift."""

    def test_drift_returns_error_and_no_backup(self, tmp_path: Path) -> None:
        """Non-dry-run upgrade blocked when drift is present; returns before backup."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=_drifted_diagnostic()):
            result = upgrade_pipeline(tmp_path)

        assert result["errors"], "Expected at least one error when drift is detected"
        assert any("Upgrade blocked" in e for e in result["errors"])
        assert any("docsmcp" in e for e in result["errors"])
        assert result.get("install_drift", {}).get("drift_detected") is True
        # Returned early — no backup should have been attempted
        assert "backup" not in result

    def test_drift_error_includes_remediation_hint(self, tmp_path: Path) -> None:
        """Error message surfaces the literal remediation command."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=_drifted_diagnostic()):
            result = upgrade_pipeline(tmp_path)

        combined = " ".join(result["errors"])
        assert "uv tool install -e --reinstall" in combined or "Reinstall" in combined

    def test_cli_ahead_upgrade_message_suggests_reload(self, tmp_path: Path) -> None:
        from tapps_mcp import __version__

        drift = InstallDriftDiagnostic(
            drift_detected=True,
            entries=[
                InstallDriftEntry(
                    binary="tapps-mcp",
                    binary_path="/fake/tapps-mcp",
                    binary_version="99.0.0",
                    source_version=__version__,
                    drifted=True,
                )
            ],
            remediation_hint="Reload MCP",
        )
        msg = format_upgrade_blocked_by_drift(drift)
        assert "Reload Cursor MCP" in msg
        assert "tapps-mcp upgrade" in msg

    def test_dry_run_bypasses_drift_gate(self, tmp_path: Path) -> None:
        """dry_run=True skips the drift gate so operators can preview despite drift."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=_drifted_diagnostic()):
            result = upgrade_pipeline(tmp_path, dry_run=True)

        drift_block_errors = [e for e in result.get("errors", []) if "Upgrade blocked" in e]
        assert not drift_block_errors, "dry_run should bypass the drift gate"

    def test_drift_block_sets_success_false(self, tmp_path: Path) -> None:
        """TAP-6952: the drift-block early return must set success=False explicitly.

        Before the fix, ``result`` had no ``success`` key on this path at all —
        callers defaulting a missing key to True (the old ``run_upgrade``
        behavior) would report a blocked upgrade as successful.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=_drifted_diagnostic()):
            result = upgrade_pipeline(tmp_path)

        assert "success" in result, "drift-block return must set the success key explicitly"
        assert result["success"] is False


class TestUpgradePipelineBackupFailureSuccessKey:
    """TAP-6952 audit: the backup-failure early return had the same gap."""

    def test_backup_failure_sets_success_false(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        # A backup target must exist for BackupManager.create_backup to be reached.
        (tmp_path / "AGENTS.md").write_text(
            "<!-- tapps-agents-version: 0.0.1 -->\n", encoding="utf-8"
        )

        no_drift = MagicMock(drift_detected=False)
        with (
            patch("tapps_mcp.diagnostics.check_install_drift", return_value=no_drift),
            patch(
                "tapps_mcp.distribution.rollback.BackupManager.create_backup",
                side_effect=OSError("disk full"),
            ),
            patch(
                "tapps_mcp.distribution.rollback.BackupManager.find_recent_backup",
                return_value=None,
            ),
        ):
            result = upgrade_pipeline(tmp_path)

        assert "success" in result, "backup-failure return must set the success key explicitly"
        assert result["success"] is False
        assert any("backup failed" in e for e in result["errors"])
