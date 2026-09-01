"""Integration tests for TAP-6897: release builds must vendor all three
packages as real copies, not editable redirects back into the checkout.

These tests run the real ``uv venv`` / ``uv pip install`` pipeline against
this checkout and assert on the built tree on disk -- not on the command
line passed to subprocess -- because that is exactly the gap TAP-6897
closes: the pre-fix command line already looked right (no ``-e`` anywhere)
while two of three packages still landed editable via
``[tool.uv.sources] ... = { workspace = true }``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tapps_mcp.distribution import blue_green as bg

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.timeout(300)]

_PACKAGES = ("tapps_core", "docs_mcp", "tapps_mcp")


def _repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(proc.stdout.strip())


def _site_packages(release_path: Path) -> Path:
    matches = list(release_path.glob("lib/python3.*/site-packages"))
    assert len(matches) == 1, f"expected exactly one site-packages dir, found {matches}"
    return matches[0]


def _dist_info_dirs(site_packages: Path, package: str) -> list[Path]:
    return sorted(site_packages.glob(f"{package}-*.dist-info"))


@pytest.fixture(scope="module")
def built_release(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build one real release into a fresh temp dir, shared by every test in
    this module -- the build itself is the expensive part, and each test
    below inspects the same tree from a different angle."""
    checkout = _repo_root()
    release_path = tmp_path_factory.mktemp("tap6897-release")
    ref = bg.ReleaseRef(version="0.0.0-tap6897", short_sha="probe", path=release_path)
    result = bg.build_release(checkout, ref, force=True)
    assert result["ok"] is True, result
    return release_path


class TestReleaseIsVendoredNotEditable:
    """Negative control (the deliverable): no editable marker of any form."""

    def test_no_editable_impl_pth_files(self, built_release: Path) -> None:
        site_packages = _site_packages(built_release)
        editable_pth = [
            p
            for p in site_packages.glob("*.pth")
            if p.name.startswith("_editable_impl_") or p.name.startswith("__editable__")
        ]
        assert editable_pth == []

    def test_no_editable_direct_url(self, built_release: Path) -> None:
        site_packages = _site_packages(built_release)
        editable_packages = []
        for package in _PACKAGES:
            dist_info_dirs = _dist_info_dirs(site_packages, package)
            assert dist_info_dirs, f"{package} dist-info missing from built release"
            for dist_info in dist_info_dirs:
                direct_url = json.loads((dist_info / "direct_url.json").read_text())
                if direct_url.get("dir_info", {}).get("editable"):
                    editable_packages.append(package)
        assert editable_packages == []


class TestReleaseIsImportable:
    """Positive control: all three packages import for real, with real
    modules present -- not just the ``tapps_core/playbooks/`` namespace
    portion that ships as real files even under an editable install."""

    def test_all_three_packages_import(self, built_release: Path) -> None:
        python = built_release / "bin" / "python"
        proc = subprocess.run(
            [str(python), "-c", "import tapps_core, docs_mcp, tapps_mcp"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr

    def test_tapps_core_has_real_modules_not_only_playbooks(self, built_release: Path) -> None:
        site_packages = _site_packages(built_release)
        entries = {p.name for p in (site_packages / "tapps_core").iterdir()}
        assert "playbooks" in entries
        assert "brain_bridge.py" in entries
        assert entries != {"playbooks"}


class TestTreesitterExtra:
    def test_treesitter_packages_present(self, built_release: Path) -> None:
        site_packages = _site_packages(built_release)
        for pkg in (
            "tree_sitter",
            "tree_sitter_typescript",
            "tree_sitter_go",
            "tree_sitter_rust",
        ):
            assert _dist_info_dirs(site_packages, pkg), f"{pkg} missing from built release"
