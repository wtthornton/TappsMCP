"""Combined TappsPlatform MCP server (thin wrapper).

See :mod:`tapps_mcp.platform.combined_server` for the full implementation.

Usage::

    python examples/combined_server.py
    python examples/combined_server.py --transport http --port 8000
"""

from __future__ import annotations

import sys


def main() -> None:
    """Parse CLI args and delegate to the platform combined server."""
    from tapps_mcp.platform.combined_server import run_combined_server

    transport = "stdio"
    host = "127.0.0.1"
    port = 8000

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--transport" and i + 1 < len(args):
            transport = args[i + 1]
            i += 2
        elif args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1

    run_combined_server(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
