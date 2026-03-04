"""Entry script for PyInstaller one-file exe. Do not use directly; run docsmcp or build via scripts/build-docsmcp-exe.ps1."""

from __future__ import annotations

from docs_mcp.cli import cli

if __name__ == "__main__":
    cli()
