#!/usr/bin/env bash
# TAP-7754 — regression test for the hook-wiring checks in
# scripts/validate-claude-plugin.sh section (c).
#
# Section (c) originally proved one direction only: every script hooks.json
# NAMES must exist in the bundle. Two defects lived in its blind spots, and
# both shipped:
#
#   1. INERT SCRIPT. The bundle shipped `hooks/tapps-pre-bash.sh` — the
#      destructive-command guard — with no hooks.json entry, so the plugin's
#      bash guard did nothing on install. Nothing was dangling, so the
#      original check was silent: the file is right there.
#
#   2. UNANCHORED COMMAND. Commands were emitted as
#      `hooks/tapps-session-start.sh`, relative to whatever directory the
#      session started in. Confirmed against a real install of this bundle
#      on 2026-09-17, before the fix:
#
#        Hook SessionStart:startup error:
#          /bin/sh: 1: hooks/tapps-session-start.sh: not found
#        Hook UserPromptSubmit error:
#          /bin/sh: 1: hooks/tapps-user-prompt-submit.sh: not found
#        SessionEnd:other [hooks/tapps-session-end.sh] completed with status 127
#
#      and after it, same probe, same session shape:
#
#        SessionStart:startup (SessionStart) success: ...
#        UserPromptSubmit (UserPromptSubmit) success: ...
#        SessionEnd:other ["${CLAUDE_PLUGIN_ROOT}/hooks/tapps-session-end.sh"]
#          completed with status 0
#
#      Every hook in the bundle was dead while parts (a)-(c) passed clean.
#
# The two are one blind spot from opposite ends — "the file exists" was being
# read as "the hook runs" — which is why they are checked, and tested, together.
#
# The controls (negative before positive for each property):
#   1.  a shipped script no event references                  -> fail
#   2.  every shipped script referenced                       -> pass
#   3.  hooks.json naming a script the bundle lacks           -> fail (part (c) still works)
#   4.  a bare relative command path                          -> fail
#   5.  a ${CLAUDE_PLUGIN_ROOT}-anchored command path         -> pass
#   6.  an absolute command path                              -> pass (documented exemption)
#   7.  an unreachable anchor this check does not know        -> fail (unknown refuses)
#   8.  unanchored bundle: UNREFERENCED counts ONLY the truly
#       unreferenced scripts, not every script in the bundle  -> exactly 1
#   9.  the real, currently-shipped plugin/claude bundle      -> pass
#
# Control 8 is not cosmetic. While this check was being written, an unanchored
# command skipped the bookkeeping that records a script as referenced, so an
# unanchored bundle reported all 15 of its scripts inert when only 2 were. Both
# verdicts were "fail", so exit status alone could not tell the two apart — and
# a count that silently becomes a count of something else is the defect
# .claude/rules/measurement-validity.md exists to catch. It asserts on the
# finding, not the exit code.
#
# Usage: bash scripts/test-validate-claude-plugin-hook-wiring.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# VALIDATOR_OVERRIDE points these fixtures at an OLDER copy of the validator
# (`git show <sha>:scripts/validate-claude-plugin.sh`) so a reviewer can watch
# each control go red there — the "run the proof against base" step that turns
# "this control passes" into "this control discriminates".
VALIDATOR="${VALIDATOR_OVERRIDE:-$REPO_ROOT/scripts/validate-claude-plugin.sh}"
SOURCE_BUNDLE="$REPO_ROOT/plugin/claude"
SCRATCH_ROOT="/tmp/claude-1000/test-validate-claude-plugin-hook-wiring.$$"

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

# Copy the real bundle so every check other than the one under test passes;
# a fixture that trips an unrelated check would fail for the wrong reason.
fixture() {
  local name="$1"
  local dest="$SCRATCH_ROOT/$name"
  mkdir -p "$dest"
  cp -r "$SOURCE_BUNDLE/." "$dest/"
  echo "$dest"
}

# Rewrite every hooks.json command through a sed expression.
rewrite_commands() {
  local hooks_json="$1/hooks/hooks.json"
  sed -i "$2" "$hooks_json"
}

# --- 1. Negative control: a shipped script nothing references. This is the
# TAP-7754 defect itself, and the shape the original part (c) could not see.
d="$(fixture 01-inert-script)"
cat >"$d/hooks/tapps-orphan-guard.sh" <<'EOF'
#!/usr/bin/env bash
# Looks like a safety control. No hooks.json event names it.
exit 0
EOF
chmod +x "$d/hooks/tapps-orphan-guard.sh"
check "1. shipped script no event references" fail "$d"

# --- 2. Anti-vacuity: the same fixture WITHOUT the orphan must pass. A check
# that rejected this too would be failing on the bundle, not on the defect.
d="$(fixture 02-no-orphan)"
check "2. every shipped script referenced" pass "$d"

# --- 3. The original direction must still work: hooks.json naming a script
# the bundle does not ship. Guards against the new code replacing part (c)
# rather than extending it.
d="$(fixture 03-dangling)"
rewrite_commands "$d" 's#tapps-session-start\.sh#tapps-does-not-exist.sh#'
check "3. hooks.json references a script the bundle lacks" fail "$d"

# --- 4. Negative control for the anchor: the exact form that shipped and
# made every hook fail with 'not found' on a real install.
d="$(fixture 04-bare-relative)"
python3 - "$d/hooks/hooks.json" <<'EOF'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))


def walk(node):
    if isinstance(node, dict):
        if node.get("type") == "command" and isinstance(node.get("command"), str):
            node["command"] = node["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "")
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for i in node:
            walk(i)


walk(data)
json.dump(data, open(p, "w", encoding="utf-8"), indent=2)
EOF
check "4. bare relative command path" fail "$d"

# --- 5. Positive control for the anchor: the shipped, fixed form.
d="$(fixture 05-plugin-root-anchored)"
check "5. \${CLAUDE_PLUGIN_ROOT}-anchored command path" pass "$d"

# --- 6. An absolute path resolves wherever it points; nothing about this
# bundle can make it right or wrong, so it is exempt by design. Proving the
# exemption fires keeps check 4 honest about WHY it rejected.
d="$(fixture 06-absolute)"
python3 - "$d/hooks/hooks.json" <<'EOF'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))


def walk(node):
    if isinstance(node, dict):
        if node.get("type") == "command" and isinstance(node.get("command"), str):
            node["command"] = '"/usr/local/bin/tapps-external-hook.sh"'
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for i in node:
            walk(i)


walk(data)
json.dump(data, open(p, "w", encoding="utf-8"), indent=2)
EOF
# Every bundled script is now unreferenced, so strip them: this control is
# about the anchor exemption alone.
find "$d/hooks" -name '*.sh' -delete
check "6. absolute command path (documented exemption)" pass "$d"

# --- 7. Unknown refuses. A placeholder this check does not recognise is
# rejected rather than waved through as "probably fine".
d="$(fixture 07-unknown-anchor)"
python3 - "$d/hooks/hooks.json" <<'EOF'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))


def walk(node):
    if isinstance(node, dict):
        if node.get("type") == "command" and isinstance(node.get("command"), str):
            node["command"] = node["command"].replace(
                "${CLAUDE_PLUGIN_ROOT}/", "${SOME_UNKNOWN_ROOT}/"
            )
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for i in node:
            walk(i)


walk(data)
json.dump(data, open(p, "w", encoding="utf-8"), indent=2)
EOF
check "7. unrecognised anchor is refused, not assumed fine" fail "$d"

# --- 8. The two findings must stay orthogonal. An unanchored bundle that
# ALSO ships one orphan must report exactly one inert script -- not every
# script it ships. Asserts on the finding, because both cases exit non-zero
# and the exit code cannot tell them apart.
d="$(fixture 08-orthogonal-counts)"
cat >"$d/hooks/tapps-orphan-guard.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$d/hooks/tapps-orphan-guard.sh"
python3 - "$d/hooks/hooks.json" <<'EOF'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))


def walk(node):
    if isinstance(node, dict):
        if node.get("type") == "command" and isinstance(node.get("command"), str):
            node["command"] = node["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "")
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for i in node:
            walk(i)


walk(data)
json.dump(data, open(p, "w", encoding="utf-8"), indent=2)
EOF
output="$(bash "$VALIDATOR" "$d" 2>&1 || true)"
inert_count="$(
  printf '%s\n' "$output" \
    | sed -n '/ships hook scripts no hooks.json event references/,/^ERROR/p' \
    | grep -c '^  - ' || true
)"
if [[ "$inert_count" == "1" ]]; then
  echo "OK: 8. inert-script count is 1, not inflated by the unanchored commands"
else
  echo "FAIL: 8. expected exactly 1 inert script, got $inert_count" >&2
  echo "$output" >&2
  FAILURES=$((FAILURES + 1))
fi

# --- 9. The real bundle, exactly as shipped.
check "9. the shipped plugin/claude bundle" pass "$SOURCE_BUNDLE"

echo
if [[ $FAILURES -ne 0 ]]; then
  echo "$FAILURES control(s) failed" >&2
  exit 1
fi
echo "All hook-wiring controls passed"
