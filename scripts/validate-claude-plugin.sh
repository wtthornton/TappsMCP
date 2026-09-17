#!/usr/bin/env bash
# Validate the Claude Code plugin bundle structure, manifest schema, and
# referential integrity between hooks.json and the scripts it points at.
set -euo pipefail

PLUGIN_DIR="${1:-plugin/claude}"

echo "Validating Claude Code plugin bundle at: $PLUGIN_DIR"

FAIL=0

# --- (a) Required files present -------------------------------------------
REQUIRED_FILES=(
  ".claude-plugin/plugin.json"
  ".claude-plugin/marketplace.json"
  "README.md"
  "LICENSE"
  "CHANGELOG.md"
  ".mcp.json"
  "hooks/hooks.json"
)

for f in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$PLUGIN_DIR/$f" ]]; then
    echo "ERROR: Missing required file: $PLUGIN_DIR/$f" >&2
    FAIL=1
  fi
done

shopt -s nullglob
skill_manifests=("$PLUGIN_DIR"/skills/*/SKILL.md)
agent_files=("$PLUGIN_DIR"/agents/*.md)
shopt -u nullglob

if [[ ${#skill_manifests[@]} -eq 0 ]]; then
  echo "ERROR: No skills/*/SKILL.md found under $PLUGIN_DIR" >&2
  FAIL=1
fi

if [[ ${#agent_files[@]} -eq 0 ]]; then
  echo "ERROR: No agents/*.md found under $PLUGIN_DIR" >&2
  FAIL=1
fi

if [[ $FAIL -ne 0 ]]; then
  echo "Plugin validation FAILED — missing required files" >&2
  exit 1
fi
echo "Required files: OK"

# --- (b) Schema — delegate to the installed Claude Code CLI ---------------
# `claude plugin validate` is the ground truth for manifest/skill/agent
# shape. Do not hand-reimplement this schema — that creates a second,
# drifting source of truth. If the CLI is missing, fail loudly rather than
# silently skipping the check: a check that passes when it could not run is
# worse than no check.
if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found on PATH — cannot run schema validation." >&2
  echo "Install/enable Claude Code, or run this script where it is available." >&2
  exit 3
fi

echo "Running: claude plugin validate $PLUGIN_DIR/.claude-plugin/marketplace.json --strict"
if ! claude plugin validate "$PLUGIN_DIR/.claude-plugin/marketplace.json" --strict; then
  echo "ERROR: marketplace.json failed schema validation" >&2
  FAIL=1
fi

# Validating plugin.json also recurses into every skill, agent, and command
# the bundle ships (confirmed empirically: pointing --strict at plugin.json
# reports "Validating skill: ..." / "Validating agent: ..." lines and fails
# on a broken SKILL.md or agent frontmatter). Validating marketplace.json
# alone does NOT recurse into skill/agent content, so both calls are
# required — marketplace.json for the marketplace entry shape, plugin.json
# for the plugin manifest plus every skill/agent/command it declares.
echo "Running: claude plugin validate $PLUGIN_DIR/.claude-plugin/plugin.json --strict"
if ! claude plugin validate "$PLUGIN_DIR/.claude-plugin/plugin.json" --strict; then
  echo "ERROR: plugin.json (and its skills/agents/commands) failed schema validation" >&2
  FAIL=1
fi

if [[ $FAIL -ne 0 ]]; then
  echo "Plugin validation FAILED — schema errors" >&2
  exit 1
fi
echo "Schema (claude plugin validate --strict): OK"

# --- (c) Referential integrity — hooks.json vs. what the bundle ships -----
# The CLI's schema check never cross-references what else the bundle ships:
# a prior bundler shipped a hooks.json pointing at scripts it never
# included, so every hook 404'd at invocation while all schema checks
# passed. Parse hooks.json, extract every script path it references, and
# assert each one exists in the bundle.
HOOKS_JSON="$PLUGIN_DIR/hooks/hooks.json"
MISSING_HOOKS="$(python3 -c "
import json
import shlex
import sys

plugin_dir, hooks_json = sys.argv[1], sys.argv[2]

with open(hooks_json, encoding='utf-8') as f:
    data = json.load(f)

commands = []


def walk(node):
    if isinstance(node, dict):
        if node.get('type') == 'command' and isinstance(node.get('command'), str):
            commands.append(node['command'])
        for value in node.values():
            walk(value)
    elif isinstance(node, list):
        for item in node:
            walk(item)


walk(data)

missing = []
for cmd in commands:
    tokens = shlex.split(cmd)
    if not tokens:
        continue
    path = tokens[0]
    if path.startswith('\${CLAUDE_PLUGIN_ROOT}/'):
        path = path[len('\${CLAUDE_PLUGIN_ROOT}/'):]
    if path.startswith('/') or '\${' in path:
        # Absolute path or an unresolved variable we don't know how to
        # anchor — not this bundle's referential-integrity concern.
        continue
    import os
    resolved = os.path.join(plugin_dir, path)
    if not os.path.isfile(resolved):
        missing.append(resolved)

for m in missing:
    print(m)
" "$PLUGIN_DIR" "$HOOKS_JSON")"

if [[ -n "$MISSING_HOOKS" ]]; then
  echo "ERROR: hooks.json references scripts that do not exist in the bundle:" >&2
  while IFS= read -r missing; do
    echo "  - $missing" >&2
  done <<<"$MISSING_HOOKS"
  FAIL=1
fi

if [[ $FAIL -ne 0 ]]; then
  echo "Plugin validation FAILED — referential integrity" >&2
  exit 1
fi
echo "Referential integrity (hooks.json -> scripts): OK"

# --- (d) Dependency resolvability -------------------------------------------
# TAP-7758: `claude plugin validate --strict` does NOT check this — a bogus
# dependency such as "totally-bogus-nonexistent-plugin-xyz@^99.99.99" passes
# it clean in every command/flag combination (verified by experiment). A
# `dependencies` entry in plugin.json names another plugin this bundle
# expects the operator to be able to install; the only marketplace this
# script can check against is the one shipped alongside this bundle, so any
# declared dependency whose plugin name is not listed in that
# marketplace.json is provably unsatisfiable from this bundle alone — which
# is exactly the shape of the defect this check exists to catch (the bundle
# used to declare "docs-mcp@^<version>" while its own marketplace.json
# listed only "tapps-mcp"). An absent or empty `dependencies` key is valid
# and passes trivially — omitting the key is the fix, not a gap to warn on.
MARKETPLACE_JSON="$PLUGIN_DIR/.claude-plugin/marketplace.json"
PLUGIN_JSON="$PLUGIN_DIR/.claude-plugin/plugin.json"

if ! DEP_CHECK_OUTPUT="$(python3 -c "
import json
import sys

plugin_json, marketplace_json = sys.argv[1], sys.argv[2]

with open(plugin_json, encoding='utf-8') as f:
    plugin_data = json.load(f)

deps = plugin_data.get('dependencies') or []
if not deps:
    sys.exit(0)

with open(marketplace_json, encoding='utf-8') as f:
    marketplace_data = json.load(f)

known = sorted(p.get('name', '') for p in marketplace_data.get('plugins', []))
known_set = set(known)

unsatisfiable = []
for dep in deps:
    name = dep.rsplit('@', 1)[0] if isinstance(dep, str) and '@' in dep else dep
    if name not in known_set:
        unsatisfiable.append(dep)

if unsatisfiable:
    print('Dependency the marketplace cannot satisfy:')
    for dep in unsatisfiable:
        print('  - ' + repr(dep))
    print('Known plugins in ' + marketplace_json + ': ' + repr(known))
    sys.exit(1)
" "$PLUGIN_JSON" "$MARKETPLACE_JSON")"; then
  echo "ERROR: $DEP_CHECK_OUTPUT" >&2
  FAIL=1
fi

if [[ $FAIL -ne 0 ]]; then
  echo "Plugin validation FAILED — dependency resolvability" >&2
  exit 1
fi
echo "Dependency resolvability: OK"

echo "Plugin validation PASSED."
