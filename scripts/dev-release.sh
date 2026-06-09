#!/usr/bin/env bash
# High-cadence local release: bump patch, scoped test, restart dev Docker (no image rebuild).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)

usage() {
  cat <<'EOF'
Usage: scripts/dev-release.sh [--skip-bump] [--skip-test] [--skip-docker] [--patch|--sync]

  --skip-bump     Do not run bump-versions.py --patch
  --skip-test     Skip scoped pytest (pre-push still runs on git push)
  --skip-docker   Skip docker compose restart
  --patch         Bump patch version (default)
  --sync          Re-align version stamps without bumping

Fast inner loop: use stdio MCP (uv run tapps-mcp serve) — no Docker required.
Docker dev:      docker compose -f docker-compose.yml -f docker-compose.dev.yml restart tapps-mcp
EOF
}

do_bump=1
do_test=1
do_docker=1
bump_mode="--patch"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-bump) do_bump=0 ;;
    --skip-test) do_test=0 ;;
    --skip-docker) do_docker=0 ;;
    --patch) bump_mode="--patch" ;;
    --sync) bump_mode="--sync" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

if [[ "$do_bump" -eq 1 ]]; then
  python3 scripts/bump-versions.py "$bump_mode"
fi

if [[ "$do_test" -eq 1 ]]; then
  paths=()
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    case "$f" in
      packages/tapps-mcp/*) paths+=("packages/tapps-mcp/tests/") ;;
      packages/tapps-core/*) paths+=("packages/tapps-core/tests/") ;;
      packages/docs-mcp/*) paths+=("packages/docs-mcp/tests/") ;;
    esac
  done < <(git diff --name-only HEAD 2>/dev/null || true)

  # Dedupe test dirs
  uniq_paths=()
  for p in "${paths[@]}"; do
    skip=0
    for u in "${uniq_paths[@]:-}"; do
      [[ "$p" == "$u" ]] && skip=1 && break
    done
    [[ "$skip" -eq 0 ]] && uniq_paths+=("$p")
  done

  if [[ ${#uniq_paths[@]} -eq 0 ]]; then
    uniq_paths=("packages/tapps-mcp/tests/")
  fi

  for tp in "${uniq_paths[@]}"; do
    echo "[dev-release] pytest $tp -m 'not slow' -n auto --maxfail=3" >&2
    uv run pytest "$tp" -m "not slow" -q --tb=line --timeout=60 -n auto --maxfail=3
  done
fi

if [[ "$do_docker" -eq 1 ]]; then
  if docker compose -f docker-compose.yml -f docker-compose.dev.yml ps -q tapps-mcp 2>/dev/null | grep -q .; then
    echo "[dev-release] restarting dev container (no rebuild)" >&2
    "${COMPOSE[@]}" restart tapps-mcp
  else
    echo "[dev-release] starting dev stack (build once)" >&2
    "${COMPOSE[@]}" up -d --build
  fi
  if curl -sf --max-time 5 http://127.0.0.1:8000/ >/dev/null 2>&1; then
    echo "[dev-release] HTTP MCP up at http://localhost:8000/mcp" >&2
  else
    echo "[dev-release] warning: HTTP probe failed — check: ${COMPOSE[*]} logs -f" >&2
  fi
fi

echo "[dev-release] done ($(git describe --tags --always 2>/dev/null || git rev-parse --short HEAD))" >&2
