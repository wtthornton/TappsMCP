#!/bin/bash
# TappsMCP SubagentStart hook
# Injects TappsMCP awareness into spawned subagents.
cat > /dev/null
echo "[TappsMCP] This project uses TappsMCP for code quality."
echo "Available MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed, tapps_memory."
exit 0
