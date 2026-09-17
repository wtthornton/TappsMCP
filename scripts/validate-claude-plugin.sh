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
#
# TAP-7754 adds the two directions this originally missed. All three are
# derived from ONE parse of hooks.json, so they cannot disagree about what
# the file says:
#
#   MISSING      hooks.json names a script the bundle does not ship. The
#                original check. A dangling reference.
#
#   UNREFERENCED the bundle ships a hook script no event references. The
#                exact mirror, and invisible to the check above because
#                nothing is dangling — the file is right there. The bundle
#                shipped `tapps-pre-bash.sh`, the destructive-command
#                guard, with no entry for it: present, plausible, and never
#                invoked. A safety control that looks active and is not is
#                worse than an absent one.
#
#   UNANCHORED   the command exists and is referenced, and still does not
#                run. Commands were emitted as `hooks/tapps-session-end.sh`
#                — relative to whatever directory the session started in,
#                not to the plugin. Observed on a real install of this
#                bundle on 2026-09-17:
#
#                  Hook SessionStart:startup error:
#                    /bin/sh: 1: hooks/tapps-session-start.sh: not found
#                  SessionEnd:other [...] completed with status 127
#
#                Every hook in the bundle was dead, while parts (a)-(c) all
#                passed: the file it names IS present. Only the command
#                fails to resolve. `${CLAUDE_PLUGIN_ROOT}` is the documented
#                placeholder for the plugin's install directory.
#
# An anchor this check does not recognise is REFUSED, not waved through —
# unknown refuses (.claude/rules/measurement-validity.md upstream in
# nlt-orchestrator). Adding one is a deliberate edit here, not a silent pass.
HOOKS_JSON="$PLUGIN_DIR/hooks/hooks.json"
HOOK_FINDINGS="$(python3 -c "
import json
import os
import shlex
import sys

plugin_dir, hooks_json = sys.argv[1], sys.argv[2]
PLUGIN_ROOT_PREFIX = '\${CLAUDE_PLUGIN_ROOT}/'

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

findings = []
referenced = set()

for cmd in commands:
    tokens = shlex.split(cmd)
    if not tokens:
        continue
    path = tokens[0]

    if path.startswith(PLUGIN_ROOT_PREFIX):
        rel = path[len(PLUGIN_ROOT_PREFIX):]
    elif path.startswith('/'):
        # An absolute path resolves wherever it points; nothing about this
        # bundle can make it right or wrong.
        continue
    else:
        findings.append(
            'UNANCHORED\t%s\t%s' % (cmd, 'not anchored at \${CLAUDE_PLUGIN_ROOT}')
        )
        # Fall through rather than skipping: this entry still NAMES a script,
        # so it must count toward 'referenced'. Skipping here would make every
        # script in an unanchored bundle look unreferenced too, and the
        # UNREFERENCED count would silently become a count of something else.
        rel = path

    referenced.add(os.path.normpath(rel))
    if not os.path.isfile(os.path.join(plugin_dir, rel)):
        findings.append('MISSING\t%s\t%s' % (cmd, os.path.join(plugin_dir, rel)))

# Every file the bundle ships under hooks/, except the manifest itself.
hooks_dir = os.path.join(plugin_dir, 'hooks')
for entry in sorted(os.listdir(hooks_dir)) if os.path.isdir(hooks_dir) else []:
    if entry == 'hooks.json' or not os.path.isfile(os.path.join(hooks_dir, entry)):
        continue
    if os.path.normpath(os.path.join('hooks', entry)) not in referenced:
        findings.append(
            'UNREFERENCED\t%s\t%s' % (entry, os.path.join(hooks_dir, entry))
        )

for line in findings:
    print(line)
" "$PLUGIN_DIR" "$HOOKS_JSON")"

report_hook_findings() {
  local kind="$1" header="$2" found=0
  while IFS=$'\t' read -r line_kind subject detail; do
    [[ "$line_kind" == "$kind" ]] || continue
    if [[ $found -eq 0 ]]; then
      echo "ERROR: $header" >&2
      found=1
    fi
    echo "  - $subject ($detail)" >&2
  done <<<"$HOOK_FINDINGS"
  [[ $found -eq 0 ]] || FAIL=1
}

if [[ -n "$HOOK_FINDINGS" ]]; then
  report_hook_findings MISSING \
    "hooks.json references scripts that do not exist in the bundle:"
  report_hook_findings UNREFERENCED \
    "the bundle ships hook scripts no hooks.json event references (they are inert on install):"
  report_hook_findings UNANCHORED \
    "hooks.json commands are not anchored at \${CLAUDE_PLUGIN_ROOT} (they will not resolve at runtime):"
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
#   4. (round 4, TAP-7753) documented, in the SAME file, under that file's
#      own ``## Degrades without`` section, AND on the explicit
#      EXTERNAL_MCP_PREFIX_ALLOWLIST below, AND NOT a spelling of this
#      bundle's own server (checked first, unconditionally).
# A prefix satisfying none of these is printed by name — including a
# namespace this bundle used to ship under (e.g. `mcp__nlt-build__`) or a
# bare pre-plugin `mcp__tapps-mcp__`, which is NOT the plugin-resolvable form
# and must be rejected, not accepted, for a plugin-registered server.
#
# --- Round 4 — why "cross-plugin-only" (round 3) was too narrow ---
# Round 3 tightened out 4 to "cross-plugin ONLY": a prefix shaped
# ``mcp__plugin_<name>_<server>__`` whose ``<name>`` is some OTHER plugin's.
# That correctly refused a bare, documented `mcp__tapps-mcp__` (this
# bundle's own bug wearing a "the docs say it is fine" costume). But it also
# refused `mcp__nlt-release-ship__docs_release_gate` — a REAL docs-mcp tool
# that `linear-release-update` genuinely calls at step 1b (TAP-7758:
# docs-mcp lives on a separate, undeclared server) — because that reference
# is not shaped like ``mcp__plugin_<name>_<server>__`` at all; it is a bare
# fleet-alias prefix naming a genuinely different, real server. The bundle
# started failing its own validator over correct, documented code.
#
# Round 4 replaces the SHAPE test ("looks like another plugin's namespace")
# with an EXPLICIT ALLOWLIST test ("is this exact prefix one we have
# actually verified exists and is genuinely referenced"). This is
# deliberately narrower than "any other plugin name", and deliberately not
# shape-based: a documented `mcp__nonexistent__` must still fail (it is not
# on the allowlist) — exactly the fig leaf a pure shape test would reopen
# for any invented name.
#
# EXTERNAL_MCP_PREFIX_ALLOWLIST (defined in the python block below) is a
# small, hand-maintained set that a future maintainer must consciously
# edit — never derived by scanning what the bundle happens to reference
# today, because that would let a typo or an invented server add itself to
# the allowlist merely by appearing once in a skill file next to a claimed
# degrade. A prefix earns a place on it only when ALL of:
#   (a) it names a real, externally-installed-or-fleet-reachable MCP server
#       this bundle does NOT and must not register or declare as a
#       dependency (see TAP-7758 / TAP-7771 above for why not), and
#   (b) a shipped skill genuinely calls a tool under that prefix today, and
#   (c) that call is documented in the SAME file under its own
#       ``## Degrades without`` section — allowlist membership WIDENS what
#       CAN be exempted, it never bypasses HOW it must be documented (gates
#       1/2/4 below still apply on top of it).
# Removing the last reference to an allowlisted prefix from the shipped
# bundle does not fail this check (an absent reference trivially satisfies
# out 3), but leaves a dead entry nothing here will catch — review this list
# whenever the bundle is regenerated.
#
# Condition 3 (own-server refusal) runs BEFORE the allowlist and is
# unconditional: `mcp__tapps-mcp__`, `mcp__tapps_mcp__` (the underscore
# legacy/typo alias — see platform_bundles.py's `_LEGACY_TOOL_PREFIXES`),
# and any `mcp__plugin_<name>_<server>__` whose `<name>` (hyphen/underscore
# normalized) is this bundle's own plugin name but is not exactly the one
# resolvable prefix, are refused no matter what the allowlist contains and
# no matter what any file documents. The plugin name and server key are
# derived from plugin.json / .mcp.json, never hardcoded.
#
# Out 4 still carries the same four gates round 3 shipped, now built on the
# allowlist instead of the shape test:
#
#   1. Per-(file, exact prefix): a file's own `## Degrades without` section
#      must name the SAME prefix found unresolved in that SAME file.
#      Documenting a prefix in one skill never excuses it anywhere else.
#   2. The heading must be a real one — a `## Degrades without` line inside a
#      fenced code block (an anti-example, say) documents nothing, and the
#      section ends at the next heading of ANY depth, so a nested `###`
#      subsection is not swallowed into it.
#   3. ALLOWLISTED EXTERNAL SERVER, own-server spellings refused first and
#      unconditionally (see "Condition 3" above).
#   4. `skills/` only. VAL-02's out says "in a SKILL"; a hook shell script
#      could otherwise self-exempt with a `# ## Degrades without` comment.
#
# scripts/test-validate-claude-plugin-prefix-resolvability.sh proves each
# gate with a fixture that BUILDS the failing state, using the REAL
# allowlisted prefixes (`mcp__plugin_linear_linear__`,
# `mcp__nlt-release-ship__`) for the gate-1/2/4 mechanical controls so a
# fixture cannot pass or fail for the wrong reason (allowlist membership vs.
# the specific gate under test).
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


# Round 4 (TAP-7753 round 4): explicit, hand-maintained allowlist. See the
# shell-comment block above this python block for what earns a place here
# and why this replaces round 3's shape-based is_cross_plugin().
EXTERNAL_MCP_PREFIX_ALLOWLIST = {
    # The independently installed Linear Claude Code plugin (OAuth-backed,
    # see .claude/rules/integration-hygiene.md). Referenced by linear-read,
    # linear-release-update, and tapps-continue-session.
    'mcp__plugin_linear_linear__',
    # docs-mcp, reached in this repo's own dev fleet under the
    # 'nlt-release-ship' alias (see fleet.paths.json / .mcp.json upstream in
    # nlt-orchestrator). linear-release-update step 1b genuinely calls
    # mcp__nlt-release-ship__docs_release_gate, a real docs-mcp tool with no
    # tapps-mcp equivalent (TAP-7758: docs-mcp is a separate, undeclared
    # server this bundle must not depend on).
    'mcp__nlt-release-ship__',
}


def _norm(name: str) -> str:
    # Hyphen/underscore normalization so mcp__tapps-mcp__ and the
    # mcp__tapps_mcp__ legacy/typo alias (platform_bundles.py's
    # _LEGACY_TOOL_PREFIXES) are recognised as the SAME own-server spelling.
    return name.replace('_', '-')


def is_own_server_prefix(prefix: str) -> bool:
    '''Condition 3: does *prefix* name THIS bundle's own server, under any
    spelling?

    Checked before, and independent of, EXTERNAL_MCP_PREFIX_ALLOWLIST —
    refused regardless of documentation and regardless of what the
    allowlist contains. plugin_name is derived from plugin.json above,
    never hardcoded, so this tracks the bundle's own identity even if the
    plugin is ever renamed.
    '''
    norm_plugin = _norm(plugin_name)
    if prefix.startswith('mcp__plugin_') and prefix.endswith('__'):
        middle = _norm(prefix[len('mcp__plugin_'):-2])
        return middle == norm_plugin or middle.startswith(norm_plugin + '-')
    if prefix.startswith('mcp__') and prefix.endswith('__'):
        mid = _norm(prefix[len('mcp__'):-2])
        return mid == norm_plugin
    return False


def is_exemptable_external(prefix: str) -> bool:
    '''Gate 3: documented AND allowlisted AND not this bundle's own server.

    Condition 3 (is_own_server_prefix) is checked FIRST so nothing on the
    allowlist can ever paper over this bundle's own bug, even if a future
    edit to EXTERNAL_MCP_PREFIX_ALLOWLIST accidentally collided with it.
    '''
    if is_own_server_prefix(prefix):
        return False
    return prefix in EXTERNAL_MCP_PREFIX_ALLOWLIST


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
    if covered and not is_exemptable_external(prefix):
        # Documented, but not exemptable: either this bundle's own server
        # under some spelling (condition 3, unconditional), or a prefix that
        # is not on EXTERNAL_MCP_PREFIX_ALLOWLIST. Report it separately so
        # the reason is legible rather than looking like an undocumented
        # oversight.
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
    print('Documented external-server graceful-degradation references (accepted):')
    for prefix, files in sorted(degraded.items()):
        shown = ', '.join(files)
        print(f'  {prefix}  (documented in {shown})')
if refused:
    print('REFUSED exemptions — documented under ## Degrades without, but NOT on')
    print('EXTERNAL_MCP_PREFIX_ALLOWLIST (or it names a server this bundle itself')
    print('provides), so it resolves to nothing inside this plugin no matter what')
    print('the prose says:')
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
