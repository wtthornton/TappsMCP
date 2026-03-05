# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for docsmcp.exe."""

import os
from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis

block_cipher = None

# Source package directories (monorepo)
pkg_docs_mcp = Path("packages/docs-mcp/src/docs_mcp")
pkg_docs_mcp_parent = Path("packages/docs-mcp/src")
pkg_tapps_core = Path("packages/tapps-core/src/tapps_core")
pkg_tapps_core_parent = Path("packages/tapps-core/src")

# Collect ALL data files (templates .j2, config .yaml, .md, py.typed)
datas = []

for root, dirs, files in os.walk(str(pkg_docs_mcp)):
    for f in files:
        if f.endswith((".md", ".yaml", ".yml", ".typed", ".j2", ".jinja2")):
            full = os.path.join(root, f)
            rel_dir = os.path.relpath(root, str(pkg_docs_mcp_parent))
            datas.append((full, rel_dir))

for root, dirs, files in os.walk(str(pkg_tapps_core)):
    for f in files:
        if f.endswith((".md", ".yaml", ".yml", ".typed")):
            full = os.path.join(root, f)
            rel_dir = os.path.relpath(root, str(pkg_tapps_core_parent))
            datas.append((full, rel_dir))

a = Analysis(
    ["scripts/run_docsmcp.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # docs_mcp top-level
        "docs_mcp",
        "docs_mcp.cli",
        "docs_mcp.server",
        "docs_mcp.server_helpers",
        "docs_mcp.server_analysis",
        "docs_mcp.server_gen_tools",
        "docs_mcp.server_git_tools",
        "docs_mcp.server_val_tools",
        "docs_mcp.server_resources",
        # config
        "docs_mcp.config",
        "docs_mcp.config.settings",
        # extractors
        "docs_mcp.extractors",
        "docs_mcp.extractors.base",
        "docs_mcp.extractors.docstring_parser",
        "docs_mcp.extractors.generic",
        "docs_mcp.extractors.models",
        "docs_mcp.extractors.python",
        "docs_mcp.extractors.type_annotations",
        # analyzers
        "docs_mcp.analyzers",
        "docs_mcp.analyzers.api_surface",
        "docs_mcp.analyzers.commit_parser",
        "docs_mcp.analyzers.dependency",
        "docs_mcp.analyzers.git_history",
        "docs_mcp.analyzers.models",
        "docs_mcp.analyzers.module_map",
        "docs_mcp.analyzers.version_detector",
        # generators
        "docs_mcp.generators",
        "docs_mcp.generators.adr",
        "docs_mcp.generators.api_docs",
        "docs_mcp.generators.changelog",
        "docs_mcp.generators.diagrams",
        "docs_mcp.generators.guides",
        "docs_mcp.generators.metadata",
        "docs_mcp.generators.readme",
        "docs_mcp.generators.release_notes",
        "docs_mcp.generators.smart_merge",
        # validators
        "docs_mcp.validators",
        "docs_mcp.validators.completeness",
        "docs_mcp.validators.drift",
        "docs_mcp.validators.freshness",
        "docs_mcp.validators.link_checker",
        # integrations
        "docs_mcp.integrations",
        "docs_mcp.integrations.tapps",
        # tapps_core deps used by docs_mcp
        "tapps_core",
        "tapps_core.common",
        "tapps_core.common.logging",
        "tapps_core.config",
        "tapps_core.config.settings",
        "tapps_core.config.feature_flags",
        "tapps_core.security",
        "tapps_core.security.path_validator",
        # Third-party hidden imports
        "click",
        "pydantic",
        "structlog",
        "yaml",
        "jinja2",
        "git",
        "anyio",
        "httpx",
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude optional heavy deps
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
    name="docsmcp",
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
