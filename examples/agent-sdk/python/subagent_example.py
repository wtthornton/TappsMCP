#!/usr/bin/env python3
"""Demonstrates registering TappsMCP subagents via the Agent SDK.

The Agent SDK's ``agents`` parameter allows defining subagents that
Claude can delegate to. This example registers a quality reviewer
subagent that uses TappsMCP tools.

Prerequisites:
  pip install claude-code-sdk
  export ANTHROPIC_API_KEY=sk-...
"""
from __future__ import annotations

import asyncio
import os
from textwrap import dedent

from claude_code_sdk import (
    AgentDefinition,
    ClaudeCodeOptions,
    McpServerConfig,
    query,
)

# Define a TappsMCP quality reviewer subagent
TAPPS_REVIEWER_AGENT = AgentDefinition(
    name="tapps-reviewer",
    description=(
        "Use proactively to review code quality, run security scans, and "
        "enforce quality gates after editing Python files."
    ),
    system_prompt=dedent("""
        You are a TappsMCP quality reviewer. When invoked:
        1. Identify which Python files were recently edited
        2. Call mcp__tapps-mcp__tapps_quick_check on each changed file
        3. If any file scores below 70, call mcp__tapps-mcp__tapps_score_file
        4. Summarize findings: file, score, top issues, suggested fixes
    """).strip(),
    tools=["Read", "Glob", "Grep"],
    model="sonnet",
    permission_mode="dontAsk",
)


async def run_with_reviewer_agent(task: str) -> None:
    """Run a task with the tapps-reviewer subagent available."""
    mcp_servers = {
        "tapps-mcp": McpServerConfig(
            command="uvx",
            args=["tapps-mcp", "serve"],
            env={"TAPPS_MCP_PROJECT_ROOT": os.getcwd()},
        ),
    }

    options = ClaudeCodeOptions(
        mcp_servers=mcp_servers,
        agents=[TAPPS_REVIEWER_AGENT],
        max_turns=10,
    )

    async for message in query(prompt=task, options=options):
        print(message)


if __name__ == "__main__":
    asyncio.run(
        run_with_reviewer_agent(
            "Review the quality of all Python files changed in the last commit."
        )
    )
