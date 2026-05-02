"""Generate tools.json files for Docker MCP registry submission.

Runs each MCP server in stdio mode, sends a tools/list request,
and saves the tool definitions to docker-mcp/<server>/tools.json.

Usage:
    uv run python scripts/generate-tools-json.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def get_tools_from_server(command: list[str], server_name: str) -> list[dict]:
    """Start an MCP server and get its tool list via stdio JSON-RPC."""
    # Send initialize + tools/list via stdin
    initialize_request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "tools-json-generator", "version": "1.0.0"},
            },
        }
    )
    tools_list_request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
    )

    stdin_data = initialize_request + "\n" + tools_list_request + "\n"

    try:
        result = subprocess.run(
            command,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        print(f"  WARN: {server_name} timed out after 30s, using empty tools list")
        return []
    except FileNotFoundError:
        print(f"  WARN: Command not found: {command[0]}, using empty tools list")
        return []

    # Parse responses (one JSON-RPC response per line)
    tools = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            response = json.loads(line)
            if response.get("id") == 2 and "result" in response:
                tools = response["result"].get("tools", [])
                break
        except json.JSONDecodeError:
            continue

    return tools


def main() -> None:
    """Generate docker-mcp/<server>/tools.json for each MCP server in this repo."""
    repo_root = Path(__file__).resolve().parent.parent
    docker_mcp_dir = repo_root / "docker-mcp"

    servers = [
        {
            "name": "tapps-mcp",
            "command": ["uv", "run", "tapps-mcp", "serve"],
            "expected_tools": 28,
        },
        {
            "name": "docs-mcp",
            "command": ["uv", "run", "docsmcp", "serve"],
            "expected_tools": 18,
        },
    ]

    for server in servers:
        name = server["name"]
        print(f"Generating tools.json for {name}...")

        tools = get_tools_from_server(server["command"], name)

        if not tools:
            print(f"  WARN: No tools returned from {name}")
            print("  Creating placeholder tools.json")
            tools_data = {"tools": [], "_note": "Placeholder — regenerate with working server"}
        else:
            print(f"  Found {len(tools)} tools (expected {server['expected_tools']})")
            tools_data = {"tools": tools}

        output_path = docker_mcp_dir / name / "tools.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(tools_data, indent=2) + "\n")
        print(f"  Wrote {output_path}")

    print("\nDone. Review docker-mcp/*/tools.json before submitting.")


if __name__ == "__main__":
    main()
