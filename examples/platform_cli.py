"""TappsPlatform CLI (thin wrapper).

See :mod:`tapps_mcp.platform.cli` for the full implementation.

Usage::

    python examples/platform_cli.py serve          # combined (default)
    python examples/platform_cli.py serve-tapps    # TappsMCP only
    python examples/platform_cli.py serve-docs     # DocsMCP only
    python examples/platform_cli.py doctor         # check availability
"""

from __future__ import annotations

from tapps_mcp.platform.cli import cli

if __name__ == "__main__":
    cli()
