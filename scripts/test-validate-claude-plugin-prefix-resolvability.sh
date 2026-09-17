#!/usr/bin/env bash
# TAP-7753 — regression test for the mcp__* tool-prefix resolvability check
# added to scripts/validate-claude-plugin.sh (section "(e)").
#
# A plugin-registered MCP server's tools are namespaced
# mcp__plugin_<pluginName>_<serverKey>__, never a bare mcp__<serverKey>__ —
# confirmed by installing two throwaway plugins and observing an executed
# tool's real namespace (see plugin/claude/README.md). Neither
# `claude plugin validate --strict` nor part (c)'s hooks.json-vs-scripts
# referential-integrity check notices a skill naming a tool that resolves to
# nothing, because neither cross-references tool-name text against what
# `.mcp.json` actually registers.
#
# This test proves the new check discriminates correctly:
#   1. Negative control (run FIRST): a deliberately bogus mcp__nonexistent__
#      reference must be named and rejected.
#   2. Anti-vacuity control: a scratch copy whose skills use the bare,
#      pre-plugin mcp__tapps-mcp__ prefix must ALSO be rejected — a check
#      that accepts that shape is the exact non-discriminating check that
#      would have certified this bundle's original defect.
#   3. Positive control: a bundle whose only mcp__* references are the
#      plugin-resolvable prefix (or a declared dependency) must PASS.
#
# NOT covered here: whether the real, currently-shipped `plugin/claude`
# bundle passes this check outright. It does not, by design of this lane's
# own findings — `mcp__nlt-linear-issues__docs_*` /
# `mcp__nlt-release-ship__docs_*` name tools that live only on the separate,
# undeclared `docs-mcp` server, and `mcp__plugin_linear_linear__` belongs to
# a different plugin this bundle cannot safely depend on (TAP-7771). Baking
# a "must pass" assertion about the real bundle into this file would assert
# something not yet true; that gap is reported in the lane's evidence
# instead of hidden behind a loosened test.
#
# Usage: bash scripts/test-validate-claude-plugin-prefix-resolvability.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-claude-plugin.sh"
SOURCE_BUNDLE="$REPO_ROOT/plugin/claude"
SCRATCH_ROOT="/tmp/claude-1000/test-validate-claude-plugin-prefix.$$"

cleanup() {
  find "$SCRATCH_ROOT" -mindepth 1 -delete 2>/dev/null || true
  rmdir "$SCRATCH_ROOT" 2>/dev/null || true
}
trap cleanup EXIT

FAILURES=0

check() {
  local label="$1"
  local expect="$2" # "pass" or "fail"
  local dir="$3"
  local rc=0
  bash "$VALIDATOR" "$dir" >/dev/null 2>&1 || rc=$?
  if [[ "$expect" == "pass" && $rc -ne 0 ]]; then
    echo "FAIL: $label — expected exit 0, got $rc" >&2
    FAILURES=$((FAILURES + 1))
  elif [[ "$expect" == "fail" && $rc -eq 0 ]]; then
    echo "FAIL: $label — expected non-zero exit, got 0" >&2
    FAILURES=$((FAILURES + 1))
  else
    echo "OK: $label (exit $rc, expected $expect)"
  fi
}

build_fixture() {
  local name="$1"
  local dest="$SCRATCH_ROOT/$name"
  mkdir -p "$dest"
  cp -r "$SOURCE_BUNDLE/." "$dest/"
  echo "$dest"
}

# A minimal single-skill fixture avoids the real bundle's own known-open
# gaps (Linear plugin, docs-mcp tools) leaking into these three controls —
# each control below is about one specific reference, not the whole bundle.
minimal_fixture() {
  local name="$1"
  local dest="$SCRATCH_ROOT/$name"
  mkdir -p "$dest/.claude-plugin" "$dest/skills/probe" "$dest/agents"
  cp "$SOURCE_BUNDLE/.claude-plugin/plugin.json" "$dest/.claude-plugin/plugin.json"
  cp "$SOURCE_BUNDLE/.mcp.json" "$dest/.mcp.json"
  cp "$SOURCE_BUNDLE/.claude-plugin/marketplace.json" "$dest/.claude-plugin/marketplace.json"
  cp "$SOURCE_BUNDLE/LICENSE" "$dest/LICENSE"
  cp "$SOURCE_BUNDLE/CHANGELOG.md" "$dest/CHANGELOG.md"
  cp "$SOURCE_BUNDLE/README.md" "$dest/README.md"
  # Full hooks/ (not just hooks.json) so part (c)'s referential-integrity
  # check — every hooks.json command must exist in the bundle — doesn't fail
  # this fixture for an unrelated reason. Real agent content so part (a)'s
  # "at least one agents/*.md" requirement is met the same way.
  cp -r "$SOURCE_BUNDLE/hooks" "$dest/hooks"
  cp "$SOURCE_BUNDLE/agents/tapps-reviewer.md" "$dest/agents/tapps-reviewer.md"
  echo "$dest"
}

# --- Negative control (run FIRST): a deliberately bogus prefix in a scratch
# copy's skill must be named and rejected.
neg_dir="$(minimal_fixture neg-bogus)"
cat >"$neg_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: negative control
allowed-tools: mcp__nonexistent__probe_tool
---
Call `mcp__nonexistent__probe_tool`.
EOF
check "negative control: bogus mcp__nonexistent__ prefix" fail "$neg_dir"

# --- Anti-vacuity control: the bare, pre-plugin mcp__tapps-mcp__ prefix must
# ALSO be rejected for a plugin-registered server. A check that passes this
# fixture is the exact non-discriminating check that would have certified
# this bundle's real, original defect.
vacuity_dir="$(minimal_fixture vacuity-bare-tapps-mcp)"
cat >"$vacuity_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: anti-vacuity control
allowed-tools: mcp__tapps-mcp__tapps_quick_check
---
Call `mcp__tapps-mcp__tapps_quick_check`.
EOF
check "anti-vacuity control: bare mcp__tapps-mcp__ prefix rejected" fail "$vacuity_dir"

# --- Positive control: only the plugin-resolvable prefix (which is what
# TAP-7753's rewrite in platform_bundles.py now produces) must PASS.
pos_dir="$(minimal_fixture pos-resolvable)"
cat >"$pos_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: positive control
allowed-tools: mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check
---
Call `mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check`.
EOF
check "positive control: plugin-resolvable prefix" pass "$pos_dir"

if [[ $FAILURES -gt 0 ]]; then
  echo "$FAILURES check(s) FAILED" >&2
  exit 1
fi
echo "All mcp__* tool-prefix resolvability checks PASSED."
