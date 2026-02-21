"""Console entry for PyInstaller one-file executable.

Calls the real CLI main() so the frozen exe behaves like ``tapps-mcp``.
"""

from __future__ import annotations

from tapps_mcp.cli import main

if __name__ == "__main__":
    main()
