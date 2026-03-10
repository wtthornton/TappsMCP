#!/bin/bash
# TappsMCP Stop hook - Memory Capture (Epic 34.5)
# Writes session quality data to .tapps-mcp/session-capture.json for
# persistence into shared memory on next session start.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
RAW_INPUT=$(cat)
ACTIVE="false"
if command -v jq &> /dev/null; then
    ACTIVE=$(echo "$RAW_INPUT" | jq -r '.stop_hook_active // "false"' 2>/dev/null)
fi
if [[ "$ACTIVE" == "true" || "$ACTIVE" == "True" ]]; then
    exit 0
fi

PROJ_DIR="${CLAUDE_PROJECT_DIR:-.}"
CAPTURE_DIR="$PROJ_DIR/.tapps-mcp"
MARKER="$CAPTURE_DIR/.validation-marker"

if [[ -f "$MARKER" ]]; then
    VALIDATED="true"
else
    VALIDATED="false"
fi

DATE_STR=$(date +"%Y-%m-%d")

FILES_EDITED=0
if command -v git &> /dev/null; then
    FILES_EDITED=$(git diff --name-only HEAD 2>/dev/null | grep -c '\.py$' || echo 0)
fi

mkdir -p "$CAPTURE_DIR"

cat > "$CAPTURE_DIR/session-capture.json" <<ENDJSON
{"date": "$DATE_STR", "validated": $VALIDATED, "files_edited": $FILES_EDITED}
ENDJSON
exit 0
