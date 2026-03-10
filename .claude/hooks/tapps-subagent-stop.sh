#!/bin/bash
# TappsMCP SubagentStop hook (Epic 36.1)
# Advises on quality validation when subagent modified Python files.
# IMPORTANT: SubagentStop does NOT support exit code 2 (advisory only).
RAW_INPUT=$(cat)
echo "Subagent completed. Run tapps_quick_check or tapps_validate_changed"
echo "on any Python files modified by this subagent."
exit 0
