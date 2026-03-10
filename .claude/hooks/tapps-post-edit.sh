#!/bin/bash
# TappsMCP PostToolUse hook (Edit/Write)
# Reminds the agent to run quality checks after file edits.
RAW_INPUT=$(cat)
FILE=""
if command -v jq &> /dev/null; then
    FILE=$(echo "$RAW_INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null)
fi
if [[ -n "$FILE" && "$FILE" =~ \.py$ ]]; then
    echo "Python file edited: $FILE"
    echo "Consider running tapps_quick_check on it."
fi
exit 0
