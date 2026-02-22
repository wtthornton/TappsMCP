#!/usr/bin/env python3
"""Basic TappsMCP + Agent SDK example.

Runs a quick quality check on a single file using the Claude Agent SDK
with TappsMCP configured as an MCP server.

Prerequisites:
  pip install claude-code-sdk
  export ANTHROPIC_API_KEY=sk-...
  export TAPPS_MCP_PROJECT_ROOT=/path/to/your/project
"""
from __future__ import annotations

import asyncio
import os
import sys

from claude_code_sdk import ClaudeCodeOptions, McpServerConfig, query


async def run_quality_check(file_path: str) -> str:
    """Run a TappsMCP quick check on a single file via the Agent SDK."""
    # Configure TappsMCP as an MCP server
    mcp_servers = {
        "tapps-mcp": McpServerConfig(
            command="uvx",
            args=["tapps-mcp", "serve"],
            env={
                "TAPPS_MCP_PROJECT_ROOT": os.environ.get(
                    "TAPPS_MCP_PROJECT_ROOT",
                    os.getcwd(),
                ),
            },
        ),
    }

    # Create options with TappsMCP and restricted tool access
    options = ClaudeCodeOptions(
        mcp_servers=mcp_servers,
        allowed_tools=["mcp__tapps-mcp__tapps_quick_check"],
        max_turns=3,
    )

    # Run the query and collect results
    result_parts: list[str] = []
    async for message in query(
        prompt=(
            f"Run tapps_quick_check on {file_path} and report "
            "the score and top issues."
        ),
        options=options,
    ):
        if hasattr(message, "content"):
            result_parts.append(str(message.content))

    return "\n".join(result_parts)


if __name__ == "__main__":
    file_to_check = sys.argv[1] if len(sys.argv) > 1 else "src/main.py"
    result = asyncio.run(run_quality_check(file_to_check))
    print(result)
