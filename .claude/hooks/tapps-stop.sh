#!/bin/bash
# TappsMCP Stop hook
# Reminds to run tapps_validate_changed but does NOT block.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
RAW_INPUT=$(cat)
ACTIVE="false"
if command -v jq &> /dev/null; then
    ACTIVE=$(echo "$RAW_INPUT" | jq -r '.stop_hook_active // "false"' 2>/dev/null)
fi
if [[ "$ACTIVE" == "true" || "$ACTIVE" == "True" ]]; then
    exit 0
fi
echo "Reminder: Run tapps_validate_changed and tapps_checklist before ending the session."
exit 0
