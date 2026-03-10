#!/bin/bash
# TappsMCP PreCompact hook
# Backs up scoring context before context window compaction.
RAW_INPUT=$(cat)
PROJ_DIR="${CLAUDE_PROJECT_DIR:-.}"
BACKUP_DIR="$PROJ_DIR/.tapps-mcp"
mkdir -p "$BACKUP_DIR"
OUT_FILE="$BACKUP_DIR/pre-compact-context.json"
echo "$RAW_INPUT" > "$OUT_FILE"
echo "[TappsMCP] Scoring context backed up to $OUT_FILE"
exit 0
