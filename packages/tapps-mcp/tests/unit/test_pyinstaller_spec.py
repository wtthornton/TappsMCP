"""Tests verifying the PyInstaller spec covers all project modules.

Prevents drift between the source tree and ``tapps_mcp.spec`` hidden imports.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_SPEC_FILE = _REPO_ROOT / "tapps_mcp.spec"
_SRC_DIR = _PACKAGE_ROOT / "src" / "tapps_mcp"


def _parse_hidden_imports(spec_path: Path) -> set[str]:
    """Extract hidden import strings from the spec file."""
    text = spec_path.read_text(encoding="utf-8")
    return set(re.findall(r'"(tapps_mcp[^"]*)"', text))


def _discover_modules(src_dir: Path) -> set[str]:
    """Discover all Python modules under the source directory.

    Returns dotted module names (e.g. ``tapps_mcp.memory.store``).
    Skips ``__init__.py`` files (the package ``__init__`` is covered by
    the parent package import like ``tapps_mcp.memory``).
    """
    modules: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        rel = py_file.relative_to(src_dir.parent)
        parts = list(rel.with_suffix("").parts)
        dotted = ".".join(parts)
        if parts[-1] == "__init__":
            # Package init — register the package itself
            modules.add(".".join(parts[:-1]))
        else:
            modules.add(dotted)
    return modules


class TestSpecCompleteness:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        if not _SPEC_FILE.exists():
            pytest.skip("tapps_mcp.spec not found")
        self.hidden_imports = _parse_hidden_imports(_SPEC_FILE)
        self.source_modules = _discover_modules(_SRC_DIR)

    def test_all_modules_have_hidden_imports(self) -> None:
        """Every Python module in src/tapps_mcp/ should appear in the spec."""
        missing = self.source_modules - self.hidden_imports
        if missing:
            missing_sorted = sorted(missing)
            msg = (
                f"{len(missing)} module(s) missing from tapps_mcp.spec hiddenimports:\n"
                + "\n".join(f"  - {m}" for m in missing_sorted)
            )
            pytest.fail(msg)

    def test_no_stale_hidden_imports(self) -> None:
        """Hidden imports should not reference modules that no longer exist.

        Excludes third-party imports (those not starting with ``tapps_mcp.``).
        """
        tapps_imports = {h for h in self.hidden_imports if h.startswith("tapps_mcp")}
        stale = tapps_imports - self.source_modules
        if stale:
            stale_sorted = sorted(stale)
            msg = f"{len(stale)} stale hidden import(s) in tapps_mcp.spec:\n" + "\n".join(
                f"  - {s}" for s in stale_sorted
            )
            pytest.fail(msg)

    def test_spec_has_data_collection(self) -> None:
        """The spec should collect .md, .yaml, .yml data files."""
        text = _SPEC_FILE.read_text(encoding="utf-8")
        assert 'endswith((".md", ".yaml", ".yml", ".typed"))' in text
