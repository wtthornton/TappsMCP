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
# --- Round 4 (TAP-7753 round 4) ---------------------------------------------
# Round 3 exempted a documented reference only when it was shaped like
# ANOTHER PLUGIN's namespace (mcp__plugin_<other>_<server>__). That correctly
# refused a bare, documented mcp__tapps-mcp__ — but it ALSO refused
# mcp__nlt-release-ship__docs_release_gate, a REAL docs-mcp tool that
# linear-release-update genuinely calls at step 1b (TAP-7758), because a bare
# fleet-alias prefix for a genuinely different real server is not shaped like
# another plugin's namespace at all. The bundle started failing its own
# validator over correct, documented code.
#
# Round 4 replaces the shape test with an EXPLICIT ALLOWLIST
# (EXTERNAL_MCP_PREFIX_ALLOWLIST in validate-claude-plugin.sh): a documented
# prefix is exempted only when it is ALSO on that allowlist, AND is not a
# spelling of this bundle's own server (checked first, unconditionally, no
# matter what the allowlist contains). This test proves the new check
# discriminates correctly, using the REAL allowlisted prefixes
# (mcp__plugin_linear_linear__, mcp__nlt-release-ship__) for every mechanical
# gate control below — a placeholder name that was never on the allowlist in
# the first place would fail for the wrong reason (not allowlisted) rather
# than for the gate defect under test, which is exactly the "fixture that
# passes/fails for the wrong reason" trap named in
# .claude/rules/verifier-controls.md upstream in nlt-orchestrator.
#
# The 15 controls (run in the order below, negative before positive for each
# prefix per the round-2/round-3 convention):
#   1.  mcp__nonexistent__, undocumented                          -> fail
#   2.  mcp__nonexistent__, documented                             -> fail (not allowlisted)
#   3.  bare mcp__tapps-mcp__, undocumented                        -> fail
#   4.  bare mcp__tapps-mcp__, documented                          -> fail (own server)
#   5.  mcp__tapps_mcp__ (underscore form), documented             -> fail (own server)
#   6.  non-resolvable mcp__plugin_tapps-mcp_*__ spelling, documented -> fail (own server)
#   7.  mcp__plugin_linear_linear__, undocumented                  -> fail
#   8.  mcp__plugin_linear_linear__, documented                    -> pass
#   9.  mcp__nlt-release-ship__, undocumented                      -> fail
#   10. mcp__nlt-release-ship__, documented                        -> pass (allowlisted external)
#   11. "## Degrades without" inside a fenced block                -> fail
#   12. prefix only in a nested ### subsection                     -> fail
#   13. hook script self-exemption                                 -> fail
#   14. cross-file documentation (different file documents it)     -> fail
#   15. the real, currently-shipped plugin/claude bundle           -> pass
# Plus one bonus regression control (not part of the 15): a bundle whose only
# mcp__* references are the plugin-resolvable prefix must PASS trivially.
#
# Usage: bash scripts/test-validate-claude-plugin-prefix-resolvability.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# VALIDATOR_OVERRIDE lets a reviewer point these same fixtures at an OLDER
# copy of the validator (`git show <sha>:scripts/validate-claude-plugin.sh`)
# and watch each control go red (or, for the two rows round 4 fixes, watch
# them go red under round 3 and green under round 4) — the "run the proof
# against base" step that turns "this control passes" into "this control
# discriminates".
VALIDATOR="${VALIDATOR_OVERRIDE:-$REPO_ROOT/scripts/validate-claude-plugin.sh}"
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

# A minimal single-skill fixture avoids the real bundle's own known-open
# gaps (Linear plugin, docs-mcp tools) leaking into these controls — each
# control below is about one specific reference, not the whole bundle.
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

# --- 1. Negative control: a deliberately bogus prefix, undocumented, must be
# named and rejected.
neg_dir="$(minimal_fixture 01-bogus-undocumented)"
cat >"$neg_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: negative control
allowed-tools: mcp__nonexistent__probe_tool
---
Call `mcp__nonexistent__probe_tool`.
EOF
check "1. mcp__nonexistent__ undocumented" fail "$neg_dir"

# --- 2. Same bogus prefix, but documented — must STILL be rejected, because
# "documented" alone is not exemption; the allowlist gate must also hold, and
# a wholly invented server never earns a place on it.
neg_doc_dir="$(minimal_fixture 02-bogus-documented)"
cat >"$neg_doc_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: negative control, documented
allowed-tools: mcp__nonexistent__probe_tool
---
Call `mcp__nonexistent__probe_tool`.

## Degrades without

- `mcp__nonexistent__` — an invented server with no real backing. Documenting
  it must not earn it a place on EXTERNAL_MCP_PREFIX_ALLOWLIST.
EOF
check "2. mcp__nonexistent__ documented (still not allowlisted)" fail "$neg_doc_dir"

# --- 3. Anti-vacuity control: the bare, pre-plugin mcp__tapps-mcp__ prefix
# must ALSO be rejected for a plugin-registered server. A check that accepts
# this fixture is the exact non-discriminating check that would have
# certified this bundle's real, original defect.
vacuity_dir="$(minimal_fixture 03-bare-tapps-mcp-undocumented)"
cat >"$vacuity_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: anti-vacuity control
allowed-tools: mcp__tapps-mcp__tapps_quick_check
---
Call `mcp__tapps-mcp__tapps_quick_check`.
EOF
check "3. bare mcp__tapps-mcp__ undocumented" fail "$vacuity_dir"

# --- 4. Documented BARE-prefix control (TAP-7753 round 3, retained round 4).
# VAL-02's out never authorises a documented reference to THIS bundle's own
# server; a bare mcp__<server>__ resolves to nothing inside a plugin no
# matter how well it is documented, and no matter what the allowlist
# contains.
doc_bare_dir="$(minimal_fixture 04-bare-tapps-mcp-documented)"
cat >"$doc_bare_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: documented bare-prefix control
allowed-tools: mcp__tapps-mcp__tapps_quick_check
---
Call `mcp__tapps-mcp__tapps_quick_check`.

## Degrades without

- `mcp__tapps-mcp__` — this documentation must NOT exempt a bare prefix for
  a plugin-registered server. Accepting it is the round-2 defect.
EOF
check "4. bare mcp__tapps-mcp__ documented (own server)" fail "$doc_bare_dir"

# --- 5. Underscore legacy/typo alias, documented (TAP-7753 round 4). Same
# own-server refusal as #4, but via the mcp__tapps_mcp__ spelling
# platform_bundles.py's _LEGACY_TOOL_PREFIXES already defends against
# upstream. Proves is_own_server_prefix normalizes hyphen/underscore rather
# than string-matching plugin_name literally.
underscore_dir="$(minimal_fixture 05-underscore-tapps_mcp-documented)"
cat >"$underscore_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: underscore own-server control
allowed-tools: mcp__tapps_mcp__tapps_quick_check
---
Call `mcp__tapps_mcp__tapps_quick_check`.

## Degrades without

- `mcp__tapps_mcp__` — the underscore spelling of this bundle's own server.
  Documentation must not exempt this either.
EOF
check "5. mcp__tapps_mcp__ (underscore) documented (own server)" fail "$underscore_dir"

# --- 6. Documented OWN-plugin, non-resolvable spelling (TAP-7753 round 3,
# retained round 4). mcp__plugin_<self>_<server-we-do-not-register>__ has the
# mcp__plugin_ SHAPE but names this bundle's own plugin, so it is this
# bundle's bug, not another server's capability. Documentation must not
# reach it either.
doc_self_dir="$(minimal_fixture 06-own-plugin-bogus-server-documented)"
cat >"$doc_self_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: documented own-plugin bogus-server control
allowed-tools: mcp__plugin_tapps-mcp_not-registered__do_stuff
---
Call `mcp__plugin_tapps-mcp_not-registered__do_stuff`.

## Degrades without

- `mcp__plugin_tapps-mcp_not-registered__` — our own plugin name, a server
  we never register. Documentation must not exempt this.
EOF
check "6. own-plugin non-resolvable spelling documented (own server)" fail "$doc_self_dir"

# --- 7 & 8. mcp__plugin_linear_linear__ — the REAL, independently installed
# Linear plugin prefix, on EXTERNAL_MCP_PREFIX_ALLOWLIST. Undocumented must
# fail (run first); documented in the same file must pass.
linear_undoc_dir="$(minimal_fixture 07-linear-undocumented)"
cat >"$linear_undoc_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: undocumented allowlisted-external control
allowed-tools: mcp__plugin_linear_linear__list_issues
---
Call `mcp__plugin_linear_linear__list_issues`. No degrade documentation below.
EOF
check "7. mcp__plugin_linear_linear__ undocumented" fail "$linear_undoc_dir"

linear_doc_dir="$(minimal_fixture 08-linear-documented)"
cat >"$linear_doc_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: documented allowlisted-external control
allowed-tools: mcp__plugin_linear_linear__list_issues
---
Call `mcp__plugin_linear_linear__list_issues`.

## Degrades without

- `mcp__plugin_linear_linear__` — belongs to the separate, independently
  installed Linear plugin. Without it, this probe skill's one step is
  unavailable, but nothing else about the skill is affected.
EOF
check "8. mcp__plugin_linear_linear__ documented (allowlisted)" pass "$linear_doc_dir"

# --- 9 & 10. mcp__nlt-release-ship__ — the REAL docs-mcp fleet-alias prefix
# linear-release-update's step 1b genuinely calls (TAP-7758), on
# EXTERNAL_MCP_PREFIX_ALLOWLIST. This is the exact pair round 3 got wrong:
# round 3 refused #10 even though it was documented, because a bare
# mcp__<server>__ shape never matched round 3's cross-plugin-only shape test.
release_undoc_dir="$(minimal_fixture 09-release-ship-undocumented)"
cat >"$release_undoc_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: undocumented allowlisted docs-mcp control
allowed-tools: mcp__nlt-release-ship__docs_release_gate
---
Call `mcp__nlt-release-ship__docs_release_gate`. No degrade documentation below.
EOF
check "9. mcp__nlt-release-ship__ undocumented" fail "$release_undoc_dir"

release_doc_dir="$(minimal_fixture 10-release-ship-documented)"
cat >"$release_doc_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: documented allowlisted docs-mcp control
allowed-tools: mcp__nlt-release-ship__docs_release_gate
---
Call `mcp__nlt-release-ship__docs_release_gate`.

## Degrades without

- `mcp__nlt-release-ship__docs_release_gate` — this tool lives only on the
  separate `docs-mcp` server, which the Claude plugin bundle does not ship
  or depend on (TAP-7758). Without it this probe skill's one step is
  unavailable.
EOF
check "10. mcp__nlt-release-ship__ documented (allowlisted external)" pass "$release_doc_dir"

# --- 11. Fenced-heading control. A "## Degrades without" heading written
# INSIDE a fenced code block is an example of the syntax, not a live
# section. Uses the REAL allowlisted mcp__nlt-release-ship__ prefix so this
# fixture would PASS but for the fence defect — isolating gate 2a from
# allowlist membership.
fence_dir="$(minimal_fixture 11-fenced-degrade-heading)"
cat >"$fence_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: fenced-heading control
allowed-tools: mcp__nlt-release-ship__docs_release_gate
---
Call `mcp__nlt-release-ship__docs_release_gate`.

Do NOT write an anti-example like this and expect it to count:

```markdown
## Degrades without

- `mcp__nlt-release-ship__docs_release_gate` — this is inside a fence.
```
EOF
check "11. fenced '## Degrades without' heading does not exempt" fail "$fence_dir"

# --- 12. Nested-subheading control. The real "## Degrades without" section
# names nothing; only an unrelated nested "### " subsection mentions the
# prefix, which must not be read as belonging to the section above. Uses the
# REAL allowlisted mcp__nlt-release-ship__ prefix so this fixture would PASS
# but for the nesting defect.
nested_dir="$(minimal_fixture 12-nested-subheading)"
cat >"$nested_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: nested-subheading control
allowed-tools: mcp__nlt-release-ship__docs_release_gate
---
Call `mcp__nlt-release-ship__docs_release_gate`.

## Degrades without

- Nothing. This section names no prefix at all.

### Unrelated subsection

This subsection mentions `mcp__nlt-release-ship__docs_release_gate` in
passing, which must not be read as documentation belonging to the section
above.
EOF
check "12. prefix in a nested ### subsection does not exempt" fail "$nested_dir"

# --- 13. Hook self-exemption control. VAL-02's out says "in a SKILL". Uses
# the REAL allowlisted mcp__plugin_linear_linear__ prefix so this fixture
# would PASS but for the skills/-only defect — a hook script must not be
# able to exempt its own unresolvable reference with a comment line.
hook_dir="$(minimal_fixture 13-hook-self-exemption)"
cat >"$hook_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: hook self-exemption control — this skill references nothing
---
This skill deliberately names no mcp__* tool. The reference under test is in
`hooks/tapps-probe-control.sh`.
EOF
# The heading must sit at column 0 to reproduce the real state: '##' is a
# perfectly valid shell comment, and an indented or '# ##'-prefixed line
# never matched the heading pattern even at base — a fixture using one
# would go red for the wrong reason instead of exercising this gate.
cat >"$hook_dir/hooks/tapps-probe-control.sh" <<'EOF'
#!/usr/bin/env bash
# Calls mcp__plugin_linear_linear__list_issues.
## Degrades without
# - mcp__plugin_linear_linear__ — a hook must not be able to exempt itself;
#   only a skill may document a graceful degradation.
exit 0
EOF
check "13. hook script cannot self-exempt via a '## Degrades without' comment" fail "$hook_dir"

# --- 14. Cross-file documentation control (TAP-7753 round 4 — the control
# round 3 never had). Gate 1 requires a file's OWN "## Degrades without"
# section to name the prefix found unresolved in that SAME file. Skill
# "probe" references the allowlisted mcp__nlt-release-ship__ prefix but does
# NOT document it; skill "other" documents that exact string under its own
# heading but never references it. Documenting a prefix in one skill must
# never excuse an undocumented reference to it in a different skill.
crossfile_dir="$(minimal_fixture 14-cross-file-documentation)"
mkdir -p "$crossfile_dir/skills/other"
cat >"$crossfile_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: cross-file control — references the prefix, documents nothing
allowed-tools: mcp__nlt-release-ship__docs_release_gate
---
Call `mcp__nlt-release-ship__docs_release_gate`. This file documents nothing
about it — see the (unrelated) `other` skill instead.
EOF
cat >"$crossfile_dir/skills/other/SKILL.md" <<'EOF'
---
name: other
description: cross-file control — documents the prefix, never calls it
---
This skill never calls `mcp__nlt-release-ship__docs_release_gate`. It only
documents it here, which must NOT excuse the `probe` skill's own
undocumented reference above.

## Degrades without

- `mcp__nlt-release-ship__docs_release_gate` — documented here, in a
  DIFFERENT file than the one that actually references it.
EOF
check "14. cross-file documentation does not exempt the referencing file" fail "$crossfile_dir"

# --- 15. Real bundle control: the currently-shipped plugin/claude bundle
# must pass outright. Round 3 shipped this same assertion as `pass` while
# the code actually failed it (the round-4 problem statement) — the fixture
# was correct, the predicate was wrong. Round 4's allowlist fixes the
# predicate; the assertion is unchanged.
check "15. real bundle: plugin/claude passes" pass "$SOURCE_BUNDLE"

# --- Bonus regression control (not part of the 15-row matrix): a bundle
# whose only mcp__* references are the plugin-resolvable prefix (needing no
# documentation or allowlist entry at all) must PASS.
pos_dir="$(minimal_fixture 16-bonus-positive-resolvable)"
cat >"$pos_dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: positive control
allowed-tools: mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check
---
Call `mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check`.
EOF
check "16. (bonus) positive control: plugin-resolvable prefix" pass "$pos_dir"

if [[ $FAILURES -gt 0 ]]; then
  echo "$FAILURES check(s) FAILED" >&2
  exit 1
fi
echo "All mcp__* tool-prefix resolvability checks PASSED."
