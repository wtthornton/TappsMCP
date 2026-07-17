#!/usr/bin/env bash
# Shared HTTP MCP fleet — thin wrapper around `tapps-mcp fleet` (ADR-0024).
set -euo pipefail

_cmd="${1:-status}"
shift || true

_blue_green="${HOME}/.tapps-mcp/current/bin/tapps-mcp"
if [[ -x "$_blue_green" ]]; then
  TAPPS_MCP_BIN="$_blue_green"
elif command -v tapps-mcp >/dev/null 2>&1; then
  TAPPS_MCP_BIN="$(command -v tapps-mcp)"
else
  echo "tapps-mcp CLI not found. Run deploy-local or uv tool install first." >&2
  exit 1
fi

case "$_cmd" in
  start|stop|status|restart|smoke|ensure|install-systemd|audit-consumers|repair-consumers)
    exec "$TAPPS_MCP_BIN" fleet "$_cmd" "$@"
    ;;
  *)
    echo "Usage: $0 {start|stop|status|restart|smoke|ensure|install-systemd|audit-consumers|repair-consumers}" >&2
    exit 2
    ;;
esac
