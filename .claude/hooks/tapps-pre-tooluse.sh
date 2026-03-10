#!/bin/bash
# TappsMCP PreToolUse hook
# Blocks dangerous Bash commands (rm -rf /, git push --force, git reset --hard, git clean -f).
RAW_INPUT=$(cat)
COMMAND=""
if command -v jq &> /dev/null; then
    COMMAND=$(echo "$RAW_INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)
fi
if [[ -z "$COMMAND" ]]; then
    exit 0
fi

DANGEROUS_PATTERNS=(
    'rm\s+-rf\s+/'
    'git\s+push\s+--force'
    'git\s+push\s+-f\b'
    'git\s+reset\s+--hard'
    'git\s+clean\s+-f'
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if echo "$COMMAND" | grep -qP "$pattern"; then
        echo "BLOCKED: Dangerous command detected: $COMMAND"
        echo "This command matches pattern '$pattern' and could cause irreversible damage."
        echo "Please use a safer alternative."
        exit 2
    fi
done
exit 0
