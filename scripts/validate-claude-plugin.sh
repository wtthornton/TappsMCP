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
#
# TAP-7758 round 2: the CLI parses a dependency's `@suffix` as a MARKETPLACE
# name, not a semver range — a fact the original check never validated. It
# split on the last `@` and checked only the plugin-name half, so
# "tapps-mcp@no-such-marketplace" passed this check clean and then failed
# exactly the same way at install as the original defect: `claude plugin
# install` exits 0, but `claude plugin list` then shows the plugin
# `✘ failed to load` with `Error: Dependency "tapps-mcp@no-such-marketplace"
# is not installed` (reproduced by experiment against a throwaway
# marketplace on 2026-09-16 — see the lane's evidence log). The only
# marketplace this script can prove exists is the one shipped alongside this
# bundle (marketplace.json's own top-level "name" field) — the same
# constraint that already limits the plugin-name half of this check. So an
# `@suffix` is satisfiable only when it equals that marketplace's own name;
# any other suffix is unknown and is rejected, not merely warned on
# ("unknown refuses" — see .claude/rules/measurement-validity.md upstream in
# nlt-orchestrator for the general principle).
#
# A bare name with no `@` at all was confirmed BY EXPERIMENT (not assumed)
# to resolve against the plugin's OWN marketplace: installing a plugin whose
# `dependencies` was `["dep-plugin"]` (no suffix), from a marketplace that
# also lists `dep-plugin`, auto-installed `dep-plugin@<that marketplace>`
# and loaded clean. So checking a bare name against this bundle's own
# `known_set` (as the original check already did) is the CORRECT behaviour,
# not a gap — left unchanged here.
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
own_marketplace_name = marketplace_data.get('name', '')

unsatisfiable = []
bad_marketplace = []
for dep in deps:
    if isinstance(dep, str) and '@' in dep:
        name, _, suffix = dep.rpartition('@')
        if suffix != own_marketplace_name:
            bad_marketplace.append(dep)
            continue
    else:
        name = dep
    if name not in known_set:
        unsatisfiable.append(dep)

if unsatisfiable or bad_marketplace:
    if unsatisfiable:
        print('Dependency the marketplace cannot satisfy (unknown plugin name):')
        for dep in unsatisfiable:
            print('  - ' + repr(dep))
        print('Known plugins in ' + marketplace_json + ': ' + repr(known))
    if bad_marketplace:
        print('Dependency names a marketplace this bundle cannot confirm exists:')
        for dep in bad_marketplace:
            print('  - ' + repr(dep))
        print('The only marketplace this bundle can verify is its own: ' + repr(own_marketplace_name))
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

# --- (e) mcp__* tool-prefix resolvability -----------------------------------
# TAP-7753: a plugin-registered MCP server's tools are namespaced
# ``mcp__plugin_<pluginName>_<serverKey>__``, never the bare
# ``mcp__<serverKey>__`` shape most of this bundle's skills/agents/hooks were
# originally written against (confirmed by installing two throwaway plugins
# and observing an executed tool's namespace — see plugin/claude/README.md).
# Neither `claude plugin validate` nor part (c)'s referential-integrity check
# above notices this: a skill can name a tool that resolves to nothing and
# both still pass clean, because neither cross-references skill/agent/hook
# tool references against what `.mcp.json` actually registers.
#
# This check derives the ONE resolvable prefix per registered `.mcp.json`
# server from plugin.json's own `name` + that server's key (never hardcoded),
# scans every `mcp__*` reference under skills/, agents/, and hooks/, and
# requires each referenced prefix to be ONE OF:
#   1. that resolvable prefix, or
#   2. traceable to a plugin named in `dependencies`, or
#   3. absent — a reference that was never made trivially satisfies this by
#      not appearing here at all, or
#   4. (TAP-7753 round 2, tightened round 3) a CROSS-PLUGIN prefix —
#      ``mcp__plugin_<name>_<server>__`` whose ``<name>`` is some OTHER
#      plugin's — documented, in the SAME file, under that file's own
#      ``## Degrades without`` section, and only in a file under ``skills/``.
# A prefix satisfying none of these is printed by name — including a
# namespace this bundle used to ship under (e.g. `mcp__nlt-build__`) or a
# bare pre-plugin `mcp__tapps-mcp__`, which is NOT the plugin-resolvable form
# and must be rejected, not accepted, for a plugin-registered server.
#
# Out 4 exists because round 1 proved references across several skills name
# tools genuinely outside this bundle's reach — most importantly a separate,
# independently installed plugin (`mcp__plugin_linear_linear__`, TAP-7771:
# this bundle cannot safely declare it a dependency without recreating the
# unsatisfiable-dependency failure TAP-7758 fixed). Three skills (linear-read,
# linear-release-update, tapps-continue-session) stay genuinely useful without
# that plugin; `linear-issue` does not — every write it performs is gated
# behind a docs-mcp tool with no fallback, so it is excluded from this bundle
# entirely (see the skill-filter in `generate_claude_plugin_bundle`) rather
# than "documented" here, because there is no true degraded mode to document.
#
# Out 4 carries FOUR independent gates, and round 2 shipped only the first
# two — a bare `mcp__tapps-mcp__` reference passed merely by naming itself
# under a `## Degrades without` heading, which is the exact defect this
# check exists to catch. Round 3 (TAP-7753) adds gates 3 and 4:
#
#   1. Per-(file, exact prefix): a file's own `## Degrades without` section
#      must name the SAME prefix found unresolved in that SAME file.
#      Documenting a prefix in one skill never excuses it anywhere else.
#   2. The heading must be a real one — a `## Degrades without` line inside a
#      fenced code block (an anti-example, say) documents nothing, and the
#      section ends at the next heading of ANY depth, so a nested `###`
#      subsection is not swallowed into it.
#   3. CROSS-PLUGIN ONLY. VAL-02's out authorises a documented reference to
#      ANOTHER PLUGIN's namespace. So the prefix must be
#      `mcp__plugin_<name>_<server>__` with `<name>` != this bundle's own
#      plugin name. A bare `mcp__<server>__` — `mcp__tapps-mcp__`,
#      `mcp__nlt-*__`, `mcp__nonexistent__` — and this bundle's own
#      `mcp__plugin_<self>_*__` in any non-resolvable spelling are refused
#      regardless of documentation: inside a plugin they resolve to nothing
#      and no prose changes that.
#   4. `skills/` only. VAL-02's out says "in a SKILL"; a hook shell script
#      could otherwise self-exempt with a `# ## Degrades without` comment.
#
# scripts/test-validate-claude-plugin-prefix-resolvability.sh proves each
# gate with a fixture that BUILDS the failing state — including a
# documented-bare-prefix fixture that must go red, without which gate 3's
# control would be vacuous.
if ! PREFIX_CHECK_OUTPUT="$(python3 -c "
import json
import re
import sys
from pathlib import Path

plugin_dir = Path(sys.argv[1])

with open(plugin_dir / '.claude-plugin' / 'plugin.json', encoding='utf-8') as f:
    plugin_data = json.load(f)
with open(plugin_dir / '.mcp.json', encoding='utf-8') as f:
    mcp_data = json.load(f)

plugin_name = plugin_data.get('name', '')
server_keys = list(mcp_data.get('mcpServers', {}).keys())
resolvable = {f'mcp__plugin_{plugin_name}_{key}__' for key in server_keys}

declared = set()
for dep in plugin_data.get('dependencies') or []:
    name = dep.split('@', 1)[0] if isinstance(dep, str) else str(dep)
    declared.add(name)

ref_re = re.compile(r'mcp__[A-Za-z0-9_-]+__')
degrade_header_re = re.compile(r'^##\s+Degrades without\b.*', re.MULTILINE)
# Gate 2b: the section ends at the next heading of ANY depth. '^##\s+\S'
# cannot match '### ...' (the third '#' is not \s), so a nested subsection
# used to be swallowed into the Degrades-without section along with every
# prefix it mentioned.
next_heading_re = re.compile(r'^#{2,}\s+\S', re.MULTILINE)
NL = chr(10)


def mask_fences(text: str) -> str:
    '''Blank out fenced code blocks, preserving length and line structure.

    Gate 2a: a '## Degrades without' heading written INSIDE a fence is an
    example of the syntax, not a live section, and must not exempt anything.
    Byte offsets are preserved, so positions found in the masked text still
    index the original text identically.
    '''
    out = []
    in_fence = False
    for line in text.split(NL):
        stripped = line.lstrip()
        if stripped.startswith('\`\`\`') or stripped.startswith('~~~'):
            in_fence = not in_fence
            out.append(' ' * len(line))
            continue
        out.append(' ' * len(line) if in_fence else line)
    return NL.join(out)


def is_cross_plugin(prefix: str) -> bool:
    '''Gate 3: does *prefix* name ANOTHER plugin's tool namespace?

    VAL-02's out authorises a documented CROSS-PLUGIN reference, and nothing
    wider. A plugin-registered server's tools are only ever reachable as
    mcp__plugin_<pluginName>_<serverKey>__, so any prefix that is not of
    that shape resolves to nothing inside a plugin no matter what prose sits
    beside it — that includes the bare mcp__<server>__ forms this bundle was
    originally written against. And a mcp__plugin_<self>_*__ spelling that
    is not in *resolvable* names a server THIS bundle does not register, so
    it is this bundle's own bug rather than someone else's plugin.
    '''
    if not (prefix.startswith('mcp__plugin_') and prefix.endswith('__')):
        return False
    middle = prefix[len('mcp__plugin_'):-2]
    if '_' not in middle:  # needs both a <name> and a <server>
        return False
    if middle == plugin_name or middle.startswith(plugin_name + '_'):
        return False
    return True


found: dict[str, set[str]] = {}
documented: dict[str, set[str]] = {}
for sub in ('skills', 'agents', 'hooks'):
    base = plugin_dir / sub
    if not base.is_dir():
        continue
    for path in sorted(base.rglob('*')):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(plugin_dir).as_posix()
        for m in ref_re.finditer(text):
            found.setdefault(m.group(0), set()).add(rel)
        # Gate 4: only a SKILL may document a graceful degradation. A hook
        # shell script could otherwise self-exempt with a
        # '# ## Degrades without' comment line.
        if not rel.startswith('skills/'):
            continue
        masked = mask_fences(text)
        doc_prefixes: set[str] = set()
        for header in degrade_header_re.finditer(masked):
            section_start = header.end()
            nxt = next_heading_re.search(masked, section_start)
            section_end = nxt.start() if nxt else len(masked)
            # Read the prefixes out of the MASKED text too, so a fenced
            # anti-example inside an otherwise-real section documents
            # nothing either.
            doc_prefixes.update(ref_re.findall(masked[section_start:section_end]))
        if doc_prefixes:
            documented[rel] = doc_prefixes

def _declared_covers(prefix: str) -> bool:
    tokens = {t for t in prefix.split('_') if t}
    return bool(declared & tokens)

def _documented_covers(prefix: str, files: set[str]) -> set[str]:
    # Files (among those actually referencing *prefix*) whose OWN
    # Degrades-without section names that SAME prefix. A different file
    # documenting the same string never covers this one.
    return {f for f in files if prefix in documented.get(f, set())}

unresolved: dict[str, list[str]] = {}
degraded: dict[str, list[str]] = {}
refused: dict[str, list[str]] = {}
for prefix, files in found.items():
    if prefix in resolvable or _declared_covers(prefix):
        continue
    covered = _documented_covers(prefix, files)
    if covered and not is_cross_plugin(prefix):
        # Documented, but NOT a cross-plugin reference: out 4 does not reach
        # it. Report it separately so the reason is legible rather than
        # looking like an undocumented oversight.
        refused[prefix] = sorted(covered)
        covered = set()
    remaining = files - covered
    if covered:
        degraded[prefix] = sorted(covered)
    if remaining:
        unresolved[prefix] = sorted(remaining)

print('Registered (resolvable) prefixes: ' + repr(sorted(resolvable)))
print('Referenced prefixes: ' + repr(sorted(found)))
if declared:
    print('Declared dependencies: ' + repr(sorted(declared)))
if degraded:
    print('Documented cross-plugin graceful-degradation references (accepted):')
    for prefix, files in sorted(degraded.items()):
        shown = ', '.join(files)
        print(f'  {prefix}  (documented in {shown})')
if refused:
    print('REFUSED exemptions — documented under ## Degrades without, but NOT a')
    print('cross-plugin mcp__plugin_<other>_<server>__ prefix, so it resolves to')
    print('nothing inside this plugin no matter what the prose says:')
    for prefix, files in sorted(refused.items()):
        shown = ', '.join(files)
        print(f'  {prefix}  (documented in {shown})')

if unresolved:
    print('UNRESOLVED mcp__* prefixes (neither registered, declared, nor documented as a graceful degradation in the same file):')
    for prefix, files in sorted(unresolved.items()):
        shown = ', '.join(files[:3]) + ('...' if len(files) > 3 else '')
        print(f'  {prefix}  (in {shown})')
    sys.exit(1)
" "$PLUGIN_DIR")"; then
  echo "ERROR:" >&2
  echo "$PREFIX_CHECK_OUTPUT" >&2
  FAIL=1
else
  echo "$PREFIX_CHECK_OUTPUT"
fi

if [[ $FAIL -ne 0 ]]; then
  echo "Plugin validation FAILED — mcp__* tool-prefix resolvability" >&2
  exit 1
fi
echo "mcp__* tool-prefix resolvability: OK"

echo "Plugin validation PASSED."
