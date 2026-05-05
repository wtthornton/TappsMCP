"""Tests for scripts/bump-versions.py — atomic release-prep gate.

TAP-1378 / TAP-1372: every release commit must bump pyproject AND refresh
the AGENTS.md `<!-- tapps-agents-version: X.Y.Z -->` stamp in the same
commit. The script is the single source of truth for the bump; CI runs
`--check` on every push to prevent the drift pattern that produced
commits 79ef6e3, 2e2f378, and 05caaaa.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "bump-versions.py"


@pytest.fixture
def bump_module() -> ModuleType:
    """Import scripts/bump-versions.py as a module (filename has a hyphen)."""
    spec = importlib.util.spec_from_file_location("bump_versions", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_repo(tmp_path: Path, bump_module: ModuleType) -> Path:
    """Build a minimal fake repo + point the script at it."""
    (tmp_path / "packages" / "tapps-core").mkdir(parents=True)
    (tmp_path / "packages" / "tapps-mcp" / "src" / "tapps_mcp" / "pipeline").mkdir(parents=True)
    (tmp_path / "packages" / "docs-mcp").mkdir(parents=True)
    (tmp_path / "npm").mkdir()
    (tmp_path / "npm-docs-mcp").mkdir()

    for sub in ("tapps-core", "tapps-mcp", "docs-mcp"):
        (tmp_path / "packages" / sub / "pyproject.toml").write_text(
            f'[project]\nname = "{sub}"\nversion = "1.0.0"\n', encoding="utf-8"
        )
    (tmp_path / "npm" / "package.json").write_text('{"version": "1.0.0"}\n', encoding="utf-8")
    (tmp_path / "npm-docs-mcp" / "package.json").write_text(
        '{"version": "1.0.0"}\n', encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text(
        "<!-- tapps-agents-version: 1.0.0 -->\n# Agents\n", encoding="utf-8"
    )
    # Copy the real templates + upgrade.py so manifest checks against the
    # real registry (smaller surface than mocking).
    src = (
        REPO_ROOT
        / "packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py"
    )
    shutil.copy(
        src,
        tmp_path / "packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py",
    )
    upgrade = REPO_ROOT / "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py"
    shutil.copy(
        upgrade,
        tmp_path / "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py",
    )

    bump_module.REPO_ROOT = tmp_path
    return tmp_path


class TestStampRewrite:
    def test_rewrite_stamp_updates_version(self, fake_repo: Path, bump_module) -> None:
        path = fake_repo / "AGENTS.md"
        old, new_content = bump_module.rewrite_stamp(path, "2.5.0")
        assert old == "1.0.0"
        assert "<!-- tapps-agents-version: 2.5.0 -->" in new_content

    def test_rewrite_stamp_raises_when_missing(self, tmp_path: Path, bump_module) -> None:
        target = tmp_path / "no-stamp.md"
        target.write_text("# no stamp here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="No tapps-agents-version stamp"):
            bump_module.rewrite_stamp(target, "2.0.0")

    def test_read_stamp_extracts_version(self, fake_repo: Path, bump_module) -> None:
        assert bump_module.read_stamp(fake_repo / "AGENTS.md") == "1.0.0"


class TestCheckMode:
    def test_passes_when_in_sync(self, fake_repo: Path, bump_module, capsys) -> None:
        rc = bump_module.run_check()
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_fails_when_stamp_lags(self, fake_repo: Path, bump_module, capsys) -> None:
        # Bump pyproject only — simulating the 79ef6e3 / 2e2f378 pattern.
        pyproject = fake_repo / "packages/tapps-mcp/pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace("1.0.0", "1.0.1"), encoding="utf-8")
        rc = bump_module.run_check()
        assert rc == 1
        out = capsys.readouterr().out
        assert "AGENTS.md" in out
        assert "1.0.0" in out and "1.0.1" in out

    def test_fails_when_manifest_has_phantom_hook(
        self, fake_repo: Path, bump_module, capsys
    ) -> None:
        # Inject a phantom hook into _CANONICAL_HOOK_MANIFEST — the
        # 05caaaa root cause (pre-tooluse.sh listed but no template).
        upgrade = fake_repo / "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py"
        content = upgrade.read_text()
        content = content.replace(
            '"tapps-session-start.sh",',
            '"tapps-session-start.sh",\n    "tapps-phantom-nope.sh",',
            1,
        )
        upgrade.write_text(content)
        rc = bump_module.run_check()
        assert rc == 1
        assert "tapps-phantom-nope.sh" in capsys.readouterr().out


class TestBumpAtomicity:
    def test_bump_refreshes_pyproject_and_stamp(
        self, fake_repo: Path, bump_module, capsys
    ) -> None:
        changes = bump_module.collect_bump_changes("patch")
        for path, _, _, content in changes:
            path.write_text(content, encoding="utf-8")

        assert (
            bump_module.read_pyproject_version(fake_repo / "packages/tapps-mcp/pyproject.toml")
            == "1.0.1"
        )
        assert bump_module.read_stamp(fake_repo / "AGENTS.md") == "1.0.1"
        # Post-bump must pass --check immediately.
        assert bump_module.run_check() == 0

    def test_bump_refuses_when_manifest_has_phantom_hook(
        self, fake_repo: Path, bump_module
    ) -> None:
        upgrade = fake_repo / "packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py"
        content = upgrade.read_text()
        upgrade.write_text(
            content.replace(
                '"tapps-session-start.sh",',
                '"tapps-session-start.sh",\n    "tapps-phantom-nope.sh",',
                1,
            )
        )
        with pytest.raises(SystemExit, match="BUMP REFUSED"):
            bump_module.collect_bump_changes("patch")


class TestUnifiedVersioning:
    """The script must keep all three packages on the same version.

    Pre-TAP-1378-followup behaviour: each package was bumped independently
    by `+1 patch`, so a session that bumped tapps-mcp four times left
    tapps-core / docs-mcp three releases behind. The unified-versioning
    fix computes the bump from `max(current versions)` once and applies
    it to every pyproject + npm + the AGENTS.md stamp.
    """

    def test_drifted_packages_bump_to_same_target(
        self, fake_repo: Path, bump_module
    ) -> None:
        # Mimic the real-world drift that motivated this change: tapps-mcp
        # ahead, the other two languishing on an older release.
        (fake_repo / "packages/tapps-mcp/pyproject.toml").write_text(
            '[project]\nname = "tapps-mcp"\nversion = "1.0.5"\n', encoding="utf-8"
        )
        (fake_repo / "AGENTS.md").write_text(
            "<!-- tapps-agents-version: 1.0.5 -->\n", encoding="utf-8"
        )
        # tapps-core + docs-mcp still at 1.0.0; npm files at 1.0.0.
        changes = bump_module.collect_bump_changes("patch")
        for path, _, _, content in changes:
            path.write_text(content, encoding="utf-8")
        # Unified target = max(1.0.5, 1.0.0, 1.0.0) bumped patch = 1.0.6.
        for rel in (
            "packages/tapps-core/pyproject.toml",
            "packages/tapps-mcp/pyproject.toml",
            "packages/docs-mcp/pyproject.toml",
        ):
            assert (
                bump_module.read_pyproject_version(fake_repo / rel) == "1.0.6"
            ), f"{rel} did not converge on the unified bump target"
        assert bump_module.read_npm_version(fake_repo / "npm/package.json") == "1.0.6"
        assert (
            bump_module.read_npm_version(fake_repo / "npm-docs-mcp/package.json") == "1.0.6"
        )
        assert bump_module.read_stamp(fake_repo / "AGENTS.md") == "1.0.6"
        # Post-bump --check must pass.
        assert bump_module.run_check() == 0

    def test_sync_realigns_without_bumping(
        self, fake_repo: Path, bump_module
    ) -> None:
        """`part=None` (the --sync mode) brings everyone to current max.

        Used as a one-time fix after drift; should NOT advance the version.
        """
        (fake_repo / "packages/tapps-mcp/pyproject.toml").write_text(
            '[project]\nname = "tapps-mcp"\nversion = "1.0.9"\n', encoding="utf-8"
        )
        (fake_repo / "AGENTS.md").write_text(
            "<!-- tapps-agents-version: 1.0.9 -->\n", encoding="utf-8"
        )
        changes = bump_module.collect_bump_changes(None)  # --sync semantics
        for path, _, _, content in changes:
            path.write_text(content, encoding="utf-8")
        for rel in (
            "packages/tapps-core/pyproject.toml",
            "packages/tapps-mcp/pyproject.toml",
            "packages/docs-mcp/pyproject.toml",
        ):
            assert bump_module.read_pyproject_version(fake_repo / rel) == "1.0.9"

    def test_check_flags_drift_between_packages(
        self, fake_repo: Path, bump_module, capsys
    ) -> None:
        """`--check` must catch a tapps-mcp / tapps-core mismatch."""
        (fake_repo / "packages/tapps-mcp/pyproject.toml").write_text(
            '[project]\nname = "tapps-mcp"\nversion = "1.0.5"\n', encoding="utf-8"
        )
        (fake_repo / "AGENTS.md").write_text(
            "<!-- tapps-agents-version: 1.0.5 -->\n", encoding="utf-8"
        )
        rc = bump_module.run_check()
        assert rc == 1
        out = capsys.readouterr().out
        assert "packages/tapps-core/pyproject.toml" in out
        assert "1.0.0" in out and "tapps-mcp 1.0.5" in out
        assert "run --sync" in out
