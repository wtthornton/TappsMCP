#!/usr/bin/env python3
"""TappsMCP CI quality gate pipeline using the Agent SDK.

Exits non-zero if any changed file fails the quality gate.

Prerequisites:
  pip install claude-code-sdk
  export ANTHROPIC_API_KEY=sk-...
"""
from __future__ import annotations

import asyncio
import os
import sys

from claude_code_sdk import ClaudeCodeOptions, McpServerConfig, query


async def run_quality_gate(preset: str = "staging") -> bool:
    """Run tapps_validate_changed for all changed files.

    Returns True if all files pass, False otherwise.
    """
    # Configure TappsMCP as an MCP server
    mcp_servers = {
        "tapps-mcp": McpServerConfig(
            command="uvx",
            args=["tapps-mcp", "serve"],
            env={"TAPPS_MCP_PROJECT_ROOT": os.getcwd()},
        ),
    }

    # Allow both session start and validation tools
    options = ClaudeCodeOptions(
        mcp_servers=mcp_servers,
        allowed_tools=[
            "mcp__tapps-mcp__tapps_session_start",
            "mcp__tapps-mcp__tapps_validate_changed",
        ],
        max_turns=5,
    )

    passed = True
    async for message in query(
        prompt=(
            f"Run tapps_session_start, then run tapps_validate_changed "
            f"with preset={preset}. If any files fail, output "
            "'GATE_FAILED'. If all pass, output 'GATE_PASSED'."
        ),
        options=options,
    ):
        content = str(getattr(message, "content", ""))
        if "GATE_FAILED" in content:
            passed = False

    return passed


if __name__ == "__main__":
    preset = sys.argv[1] if len(sys.argv) > 1 else "staging"
    result = asyncio.run(run_quality_gate(preset))
    if not result:
        print("Quality gate FAILED", file=sys.stderr)
        sys.exit(1)
    print("Quality gate PASSED")
