#!/usr/bin/env bash
# TAP-7758 — regression test for the dependency-resolvability check added to
# scripts/validate-claude-plugin.sh (section "(d) Dependency resolvability").
#
# `claude plugin validate --strict` does not check whether a manifest's
# `dependencies` entries name a plugin the marketplace can actually satisfy
# (verified by experiment: a bogus dependency passes it clean in every
# command/flag combination). This test proves scripts/validate-claude-plugin.sh
# closes that hole: it must FAIL on a bundle whose manifest declares an
# unsatisfiable dependency, and PASS on a bundle with no `dependencies` key
# (the fixed contract) or a satisfiable one.
#
# TAP-7758 round 2 added coverage for the marketplace-suffix half of a
# dependency string: the CLI parses `name@suffix` with `suffix` as a
# MARKETPLACE name, not a semver range, and the original check validated
# only `name`. Confirmed by experiment (throwaway marketplace + plugin
# install) on 2026-09-16: `tapps-mcp@no-such-marketplace` installs with
# exit 0 and then shows `✘ failed to load` in `claude plugin list` — the
# identical failure class TAP-7758 exists to catch, just shifted to the
# other half of the string. This harness is wired into
# .github/workflows/plugin-validation.yml as its own step so a future
# regression in either half is caught on every PR, not only when a human
# remembers to run this file by hand.
#
# Usage: bash scripts/test-validate-claude-plugin-deps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/validate-claude-plugin.sh"
SOURCE_BUNDLE="$REPO_ROOT/plugin/claude"
SCRATCH_ROOT="/tmp/claude-1000/test-validate-claude-plugin-deps.$$"

# Derive the bundle's own marketplace name from marketplace.json itself
# rather than hardcoding it — the whole point of this check is that the
# CLI resolves an `@suffix` against a REAL marketplace name, so the test
# must track whatever that file actually says, not a copy of it.
OWN_MARKETPLACE_NAME="$(python3 -c "
import json
with open('$SOURCE_BUNDLE/.claude-plugin/marketplace.json', encoding='utf-8') as f:
    print(json.load(f)['name'])
")"

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

# --- Negative control: an unsatisfiable dependency the marketplace does not
# list. This must run BEFORE the positive control — a check only ever shown
# green is a positive control wearing the wrong label.
neg_dir="$(build_fixture neg-unsatisfiable)"
python3 -c "
import json
import sys

path = sys.argv[1]
with open(path, encoding='utf-8') as f:
    data = json.load(f)
data['dependencies'] = ['totally-bogus-nonexistent-plugin-xyz@^99.99.99']
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "$neg_dir/.claude-plugin/plugin.json"
check "negative control: unsatisfiable dependency" fail "$neg_dir"

# --- Negative control (round 2, TAP-7758): a dependency whose PLUGIN NAME is
# real but whose `@suffix` names a marketplace this bundle cannot confirm
# exists. The suffix is a marketplace name, not a semver range — confirmed
# by experiment (see header) — and the original check validated only the
# name half, so this exact shape (real name, bogus marketplace) sailed
# through as "OK" and then failed to load at actual install time.
neg_marketplace_dir="$(build_fixture neg-bogus-marketplace-suffix)"
python3 -c "
import json
import sys

path = sys.argv[1]
with open(path, encoding='utf-8') as f:
    data = json.load(f)
data['dependencies'] = ['tapps-mcp@no-such-marketplace']
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "$neg_marketplace_dir/.claude-plugin/plugin.json"
check "negative control: real name, bogus marketplace suffix" fail "$neg_marketplace_dir"

# --- Positive control (round 2, TAP-7758): a dependency naming a real
# plugin at THIS bundle's own marketplace name — this must still PASS. A
# check that rejects a genuinely satisfiable dependency is over-corrected
# and is as wrong as one that accepts an unsatisfiable one.
pos_marketplace_dir="$(build_fixture pos-satisfiable-marketplace-suffix)"
python3 -c "
import json
import sys

path, marketplace_name = sys.argv[1], sys.argv[2]
with open(path, encoding='utf-8') as f:
    data = json.load(f)
data['dependencies'] = [f'tapps-mcp@{marketplace_name}']
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "$pos_marketplace_dir/.claude-plugin/plugin.json" "$OWN_MARKETPLACE_NAME"
check "positive control: satisfiable name@own-marketplace" pass "$pos_marketplace_dir"

# --- TAP-7771: a dependency on a plugin in a genuinely different, real
# marketplace (not this bundle's own) is a legitimate shape, and was
# wrongly refused identically to the "no-such-marketplace" case above.
# The fix distinguishes "this bundle cannot verify" from "this bundle
# has confirmed invalid" via TRUSTED_DEPENDENCY_MARKETPLACES, an env var
# read only by this validation run -- NOT a plugin.json field, because
# `claude plugin validate --strict` (section (b), run before this
# section) turns any unrecognized manifest key into a hard failure
# (confirmed by experiment). This fixture uses the identical dependency
# string as the "no-such-marketplace" negative control's shape (real
# name, external suffix) but supplies the env var vouching for that
# marketplace, and must PASS -- while the negative control above, which
# supplies no such var, must keep failing. It is expected to FAIL red
# against the unfixed check, run first, below.
pos_cross_marketplace_dir="$(build_fixture pos-cross-marketplace)"
python3 -c "
import json
import sys

path = sys.argv[1]
with open(path, encoding='utf-8') as f:
    data = json.load(f)
data['dependencies'] = ['linear@claude-plugins-official']
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "$pos_cross_marketplace_dir/.claude-plugin/plugin.json"
rc=0
TRUSTED_DEPENDENCY_MARKETPLACES="claude-plugins-official" bash "$VALIDATOR" "$pos_cross_marketplace_dir" >/dev/null 2>&1 || rc=$?
if [[ $rc -ne 0 ]]; then
  echo "FAIL: positive control: vouched-for cross-marketplace dependency — expected exit 0, got $rc" >&2
  FAILURES=$((FAILURES + 1))
else
  echo "OK: positive control: vouched-for cross-marketplace dependency (exit $rc, expected pass)"
fi

# --- Positive control: the real, currently-shipped bundle (no `dependencies`
# key under the TAP-7758 fix, or a satisfiable one) must pass.
check "positive control: shipped bundle" pass "$SOURCE_BUNDLE"

if [[ $FAILURES -gt 0 ]]; then
  echo "$FAILURES check(s) FAILED" >&2
  exit 1
fi
echo "All dependency-resolvability checks PASSED."
