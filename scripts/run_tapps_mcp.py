"""Entry script for PyInstaller one-file exe. Do not use directly; run tapps-mcp or build via scripts/build-exe.ps1."""

from __future__ import annotations

from tapps_mcp.cli import main

if __name__ == "__main__":
    main()
