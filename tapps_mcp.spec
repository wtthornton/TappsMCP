# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for tapps-mcp.exe."""

import os
import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis

block_cipher = None

# Source package directories (monorepo)
pkg_tapps_mcp = Path("packages/tapps-mcp/src/tapps_mcp")
pkg_tapps_mcp_parent = Path("packages/tapps-mcp/src")
pkg_tapps_core = Path("packages/tapps-core/src/tapps_core")
pkg_tapps_core_parent = Path("packages/tapps-core/src")

# Collect ALL data files (knowledge .md, prompts .md, config .yaml, py.typed)
datas = []

for root, dirs, files in os.walk(str(pkg_tapps_mcp)):
    for f in files:
        if f.endswith((".md", ".yaml", ".yml", ".typed")):
            full = os.path.join(root, f)
            rel_dir = os.path.relpath(root, str(pkg_tapps_mcp_parent))
            datas.append((full, rel_dir))

for root, dirs, files in os.walk(str(pkg_tapps_core)):
    for f in files:
        if f.endswith((".md", ".yaml", ".yml", ".typed")):
            full = os.path.join(root, f)
            rel_dir = os.path.relpath(root, str(pkg_tapps_core_parent))
            datas.append((full, rel_dir))

# TAP-7423: the scaffolded one-pager template ships as a packaged .html file
# asset, an extension the walk above does not collect.
datas.append((str(pkg_tapps_mcp / "templates" / "one-pager.html"), 'tapps_mcp/templates'))


def _discover_modules(src_dir: Path) -> list[str]:
    """Enumerate every importable module under a source package directory.

    Derived rather than hand-listed (TAP-7768): a module added to the tree is
    covered the moment it exists, and a deleted one cannot leave a stale entry
    behind. An ``__init__.py`` registers its package rather than itself.
    """
    modules = set()
    for py_file in src_dir.rglob("*.py"):
        parts = list(py_file.relative_to(src_dir.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            modules.add(".".join(parts[:-1]))
        else:
            modules.add(".".join(parts))
    return sorted(modules)


a = Analysis(
    ["scripts/run_tapps_mcp.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Third-party hidden imports. These are not in the source tree, so
        # nothing can derive them; test_pyinstaller_spec.py checks they still
        # resolve rather than that they are merely listed.
        "click",
        "pydantic",
        "pydantic_settings",
        "structlog",
        "yaml",
        "anyio",
        "httpx",
        "filelock",
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        # Every tapps_mcp module, derived from the tree exactly as `datas`
        # above is. TAP-7768: this used to be ~408 hand-typed names. It drifted
        # -- one module missing, four duplicated -- and the drift could only be
        # caught after it shipped. Deriving it removes the class.
        *_discover_modules(pkg_tapps_mcp),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude optional heavy deps that aren't needed for core functionality
        "faiss",
        "sentence_transformers",
        "numpy",
        "torch",
        "transformers",
        # Exclude dev deps
        "pytest",
        "mypy",
        "ruff",
        "pre_commit",
        "playwright",
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="tapps-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
