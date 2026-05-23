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
from tapps_mcp.diagnostics import check_install_drift
from tapps_mcp.distribution.doctor import (
    check_binary_version_mismatch,
    check_docsmcp_binary_version_mismatch,
)


def _mock_completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["mock"], returncode=returncode, stdout=stdout, stderr="")


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
        assert "uv tool install -e --reinstall" in result.remediation_hint
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.binary == "tapps-mcp"
        assert entry.binary_version == "99.0.0"
        assert entry.source_version == tapps_v
        assert entry.drifted is True

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
        assert "uv tool install -e --reinstall" in combined

    def test_dry_run_bypasses_drift_gate(self, tmp_path: Path) -> None:
        """dry_run=True skips the drift gate so operators can preview despite drift."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=_drifted_diagnostic()):
            result = upgrade_pipeline(tmp_path, dry_run=True)

        drift_block_errors = [e for e in result.get("errors", []) if "Upgrade blocked" in e]
        assert not drift_block_errors, "dry_run should bypass the drift gate"
