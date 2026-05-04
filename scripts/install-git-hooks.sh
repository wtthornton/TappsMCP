#!/usr/bin/env bash
# scripts/install-git-hooks.sh
#
# Configure git to use repo-tracked hooks under .githooks/ instead of the
# default per-checkout .git/hooks/ directory. Idempotent — safe to run
# multiple times. Run once per fresh clone.
#
# This is the ONLY way the pre-push test gate (.githooks/pre-push) gets
# activated, since git ignores hook scripts checked into the repo unless
# core.hooksPath is set explicitly.

set -euo pipefail

if [[ ! -d .git ]]; then
  echo "scripts/install-git-hooks.sh: must be run from the repo root (no .git/ here)" >&2
  exit 1
fi

if [[ ! -d .githooks ]]; then
  echo "scripts/install-git-hooks.sh: .githooks/ directory not found in repo" >&2
  exit 1
fi

current="$(git config --local --get core.hooksPath || echo "")"
if [[ "$current" == ".githooks" ]]; then
  echo "core.hooksPath already set to .githooks — nothing to do."
else
  git config --local core.hooksPath .githooks
  echo "Configured core.hooksPath=.githooks (was: '${current:-<unset>}')."
fi

# Verify hooks are executable (git won't run non-executable hooks).
for hook in .githooks/*; do
  [[ -f "$hook" ]] || continue
  if [[ ! -x "$hook" ]]; then
    chmod +x "$hook"
    echo "Marked $hook executable."
  fi
done

echo
echo "Installed. Active hooks under .githooks/:"
ls -1 .githooks/ | sed 's/^/  - /'
echo
echo "To bypass the pre-push test gate in an emergency:"
echo "  TAPPS_SKIP_PREPUSH=1 git push"
echo "(Bypasses are logged to .tapps-mcp/.bypass-log.jsonl.)"
