# PyInstaller spec for tapps-mcp one-file Windows executable.
# Run from repo root: pyinstaller tapps-mcp.spec
# Output: dist/tapps-mcp.exe

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Ensure tapps_mcp and all subpackages (including tools.checklist) are included
hiddenimports = collect_submodules("tapps_mcp")
datas = collect_data_files("tapps_mcp")

# Repo root and src for analysis
repo_root = Path(SPECPATH)
pathex = [str(repo_root / "src")]

a = Analysis(
    [str(repo_root / "scripts" / "tapps_mcp_console.py")],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

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
)
