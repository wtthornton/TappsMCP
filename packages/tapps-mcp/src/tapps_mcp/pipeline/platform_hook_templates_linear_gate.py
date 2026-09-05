"""Linear cache-first read gate and session-start gate hook templates.

Split out of ``platform_hook_templates.py`` (TAP-6598) to bring that
file back under the maintainability-index gate — this module carries no
logic changes, only a physical move of the Linear cache-gate and
session-start-gate script constants.
"""

from __future__ import annotations

from typing import Any

from tapps_mcp.pipeline.linear_mcp_names import (
    apply_linear_host_placeholders,
    patch_linear_hook_matchers,
    resolve_linear_script_map,
)

# ---------------------------------------------------------------------------
# Ledger root resolution (TAP-6928)
# ---------------------------------------------------------------------------
# CLAUDE_PROJECT_DIR is trusted verbatim when set — Claude Code populates it
# with the project root. But in a linked worktree session it can be unset,
# and the naive `${CLAUDE_PROJECT_DIR:-$PWD}` fallback then resolves to the
# worktree's own cwd, splitting the bypass ledger across every worktree
# instead of the one primary-checkout file an operator audits. The fallback
# instead asks git for --git-common-dir, which is identical across a repo's
# primary checkout and all its linked worktrees (same fix shape as
# git_hooks.py's GIT_PRE_COMMIT_SCRIPT for TAP-6931).
LEDGER_ROOT_RESOLVE_BASH = """\
ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$ROOT" ]; then
  _common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$_common" ]; then
    ROOT="$(cd "$_common/.." && pwd)"
  else
    ROOT="$PWD"
  fi
fi"""

LEDGER_ROOT_RESOLVE_PS = """\
$root = $env:CLAUDE_PROJECT_DIR
if (-not $root) {
    $commonDir = $null
    try { $commonDir = (git rev-parse --path-format=absolute --git-common-dir 2>$null) } catch {}
    if ($LASTEXITCODE -eq 0 -and $commonDir) {
        $root = (Resolve-Path (Join-Path $commonDir '..')).Path
    } else {
        $root = $PWD.Path
    }
}"""

# ---------------------------------------------------------------------------
# Linear cache-first read gate (TAP-1224) — opt-in via linear_enforce_cache_gate
# ---------------------------------------------------------------------------
# Two cooperating hooks gate raw mcp__plugin_linear_linear__list_issues calls
# behind a tapps_linear_snapshot_get sentinel. Mirrors TAP-981's save_issue
# pattern. Sentinels are per-(team, project, state, label, limit) so a
# snapshot_get for project A does NOT unlock list_issues for project B.
#
# The post-snapshot-get hook writes a sentinel on BOTH cached=true and
# cached=false responses — a hit means the agent did the right thing; a miss
# means the agent is authorized to call list_issues for that exact slice.
#
# Mode is baked into the pre-list script at install time via the
# __CACHE_GATE_MODE__ placeholder ("warn" or "block"). When mode=warn,
# violations are logged to .tapps-mcp/.cache-gate-violations.jsonl and the
# call is allowed through. When mode=block, the call is rejected with exit 2.

LINEAR_CACHE_GATE_KEY_PY = """\
import sys, json, hashlib
try:
    d = json.load(sys.stdin)
except Exception:
    print('')
    print('')
    print('')
    print('')
    sys.exit(0)
name = d.get('tool_name') or d.get('toolName') or ''
inp = d.get('tool_input') or d.get('toolInput') or {}
team = (inp.get('team') or '').strip()
project = (inp.get('project') or '').strip()
state = (inp.get('state') or '').strip()
label = (inp.get('label') or '').strip()
try:
    limit = int(inp.get('limit') or 50)
except Exception:
    limit = 50
# Open-bucket alias: tapps-mcp's TTL bucket 'open' covers backlog, unstarted,
# started, triage. The skill tells agents to snapshot_get(state='open') and
# then list_issues with a concrete state. TAP-4588: canonicalize any open
# alias ('' / 'open' / bucket member) to ONE token so the payload key and the
# sentinel key converge — matching server _canonical_state. limit is dropped
# from the hash (enforced at read time via the superset fallback). Same logic
# on both sides — see server_linear_tools._resolve_cache_key.
OPEN_BUCKET = ('backlog', 'unstarted', 'started', 'triage')
state_lc = state.lower()
def _canon_state(s):
    s_lc = (s or '').strip().lower()
    if s_lc == '' or s_lc == 'open' or s_lc in OPEN_BUCKET:
        return 'open'
    return s_lc
def _key_for(state_part: str) -> str:
    canon = _canon_state(state_part)
    filt = {k: v for k, v in sorted({
        'state': canon, 'label': label,
    }.items()) if v not in (None, '')}
    payload = json.dumps(filt, sort_keys=True, default=str).encode('utf-8')
    fhash = hashlib.sha256(payload).hexdigest()[:16]
    parts = [
        (team.replace('/', '_') or '_'),
        (project.replace('/', '_') or '_'),
        (canon.replace('/', '_') or 'any'),
        fhash,
    ]
    return '__'.join(parts)
key = _key_for(state)
# With canonicalization every open-bucket alias resolves to the same key, so
# the alias set is a singleton ({key}). We still emit the bucket variants and
# de-dup so the set matches the Python _alias_keys contract byte-for-byte.
alias_keys = []
if not team or not project:
    key = ''
else:
    if state_lc in OPEN_BUCKET or state_lc in ('open', ''):
        for m in OPEN_BUCKET:
            alias_keys.append(_key_for(m))
        alias_keys.append(_key_for('open'))
        alias_keys.append(_key_for(''))
    # de-dup while preserving order; drop the exact key
    seen = {key}
    alias_keys = [k for k in alias_keys if not (k in seen or seen.add(k))]
print(name)
print(key)
print(team)
print(project)
print('|'.join(alias_keys))
"""

LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT = (
    """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook — Linear cache-gate sentinel writer (TAP-1224)
# Writes a per-(team, project, state, label, limit) sentinel on BOTH
# cached=true and cached=false responses from tapps_linear_snapshot_get.
# Paired with tapps-pre-linear-list.sh which reads the sentinel to gate
# downstream list_issues calls.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYBIN" ]; then
  exit 0
fi
PARSED=$(echo "$INPUT" | "$PYBIN" -c "
"""
    + LINEAR_CACHE_GATE_KEY_PY
    + """\
" 2>/dev/null)
TOOL=$(echo "$PARSED" | sed -n '1p')
KEY=$(echo "$PARSED" | sed -n '2p')
ALIASES=$(echo "$PARSED" | sed -n '5p')
case "$TOOL" in
  mcp__tapps-mcp__tapps_linear_snapshot_get|mcp__nlt-linear-issues__tapps_linear_snapshot_get|tapps_linear_snapshot_get) ;;
  *) exit 0 ;;
esac
if [ -z "$KEY" ]; then
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
NOW=$(date +%s)
echo "$NOW" > "$ROOT/.tapps-mcp/.linear-snapshot-sentinel-${KEY}" 2>/dev/null
# TAP-1374: also write bucket-alias sentinels so a snapshot for state='open'
# (a tapps-mcp TTL bucket alias) unlocks list_issues for any open-bucket
# member state without self-tripping the gate.
if [ -n "$ALIASES" ]; then
  IFS='|' read -r -a _ALIAS_KEYS <<< "$ALIASES"
  for ak in "${_ALIAS_KEYS[@]}"; do
    [ -z "$ak" ] && continue
    echo "$NOW" > "$ROOT/.tapps-mcp/.linear-snapshot-sentinel-${ak}" 2>/dev/null
  done
fi
exit 0
"""
)

LINEAR_CACHE_GATE_PRE_LIST_SCRIPT = (
    """\
#!/usr/bin/env bash
# TappsMCP PreToolUse hook — Linear cache-first read gate (TAP-1224)
# Gates raw mcp__plugin_linear_linear__list_issues calls behind a recent
# tapps_linear_snapshot_get sentinel for the same (team, project, state,
# label, limit) slice (within 300s). Mode is baked in at install time:
# "warn" logs to .cache-gate-violations.jsonl and allows; "block" exits 2.
# Bypass with TAPPS_LINEAR_SKIP_CACHE_GATE=1 (logged to .bypass-log.jsonl).
MODE="__CACHE_GATE_MODE__"
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYBIN" ]; then
  # No python available — cannot compute key; fail-open for portability.
  exit 0
fi
PARSED=$(echo "$INPUT" | "$PYBIN" -c "
"""
    + LINEAR_CACHE_GATE_KEY_PY
    + """\
" 2>/dev/null)
TOOL=$(echo "$PARSED" | sed -n '1p')
KEY=$(echo "$PARSED" | sed -n '2p')
CALL_TEAM=$(echo "$PARSED" | sed -n '3p')
CALL_PROJECT=$(echo "$PARSED" | sed -n '4p')
case "$TOOL" in
  __LINEAR_LIST_ISSUES_CASE__) ;;
  *) exit 0 ;;
esac
if [ -z "$KEY" ]; then
  exit 0
fi
"""
    + LEDGER_ROOT_RESOLVE_BASH
    + """
if [ "${TAPPS_LINEAR_SKIP_CACHE_GATE:-0}" = "1" ]; then
  mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
  echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"bypass\\":\\"TAPPS_LINEAR_SKIP_CACHE_GATE\\",\\"key\\":\\"${KEY}\\"}" \\
    >> "$ROOT/.tapps-mcp/.bypass-log.jsonl" 2>/dev/null
  exit 0
fi
SENTINEL="$ROOT/.tapps-mcp/.linear-snapshot-sentinel-${KEY}"
if [ -f "$SENTINEL" ]; then
  NOW=$(date +%s)
  SENT=$(cat "$SENTINEL" 2>/dev/null)
  if echo "$SENT" | grep -Eq '^[0-9]+$'; then
    AGE=$((NOW - SENT))
    if [ "$AGE" -le 300 ]; then
      exit 0
    fi
  fi
fi
# No matching sentinel (or stale). Determine violation category before logging.
# TAP-1411: cross-project reads (allowed by agent-scope.md) must NOT be
# treated as gate misses. Read expected team/project from .tapps-mcp.yaml
# (linear_team / linear_project flat keys); if the call's team/project differ,
# tag category=cross_project and pass through even in block mode.
EXPECTED_TEAM=""
EXPECTED_PROJECT=""
if [ -f "$ROOT/.tapps-mcp.yaml" ]; then
  EXPECTED_TEAM=$(grep -E '^linear_team:' "$ROOT/.tapps-mcp.yaml" 2>/dev/null | head -1 | sed -E 's/^linear_team:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\\1/')
  EXPECTED_PROJECT=$(grep -E '^linear_project:' "$ROOT/.tapps-mcp.yaml" 2>/dev/null | head -1 | sed -E 's/^linear_project:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\\1/')
fi
CATEGORY="gate_miss"
if [ -n "$EXPECTED_TEAM" ] && [ -n "$EXPECTED_PROJECT" ] && [ -n "$CALL_TEAM" ] && [ -n "$CALL_PROJECT" ]; then
  if [ "$CALL_TEAM" != "$EXPECTED_TEAM" ] || [ "$CALL_PROJECT" != "$EXPECTED_PROJECT" ]; then
    CATEGORY="cross_project"
  fi
fi
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"key\\":\\"${KEY}\\",\\"mode\\":\\"${MODE}\\",\\"category\\":\\"${CATEGORY}\\",\\"call_team\\":\\"${CALL_TEAM}\\",\\"call_project\\":\\"${CALL_PROJECT}\\"}" \\
  >> "$ROOT/.tapps-mcp/.cache-gate-violations.jsonl" 2>/dev/null
# Cross-project reads pass through regardless of mode — agent-scope.md allows
# read-only access to other projects; the gate is for THIS project's writes.
if [ "$CATEGORY" = "cross_project" ]; then
  exit 0
fi
if [ "$MODE" = "warn" ]; then
  cat >&2 <<MSG
[TappsMCP refusal layer=hook-only/defense-in-depth] Primary gate is the tapps_linear_list_issues server tool (TAP-2008 Agent Gateway). This hook is the fallback layer — it fired because the raw Linear plugin was called directly instead of through the wrapper.
TappsMCP: Linear cache-first read rule (TAP-1224, warn mode) — no recent tapps_linear_snapshot_get for this (team, project, state) slice.
Route reads through the \\`linear-read\\` skill (TAP-1260):
  1. tapps_linear_snapshot_get(team, project, state)
  2. On cached=false: list_issues with the same filters, then tapps_linear_snapshot_put.
This call is allowed (warn mode) but logged to .tapps-mcp/.cache-gate-violations.jsonl.
See .claude/rules/linear-standards.md.
MSG
  exit 0
fi
cat >&2 <<MSG
[TappsMCP refusal layer=hook-only/defense-in-depth] Primary gate is the tapps_linear_list_issues server tool (TAP-2008 Agent Gateway). This hook is the fallback layer — it fired because the raw Linear plugin was called directly instead of through the wrapper.
TappsMCP: Blocked mcp__plugin_linear_linear__list_issues — no recent tapps_linear_snapshot_get for this (team, project, state) slice.
Route reads through the \\`linear-read\\` skill (TAP-1260):
  1. tapps_linear_snapshot_get(team, project, state)
  2. On cached=true: filter in memory (no Linear call).
  3. On cached=false: list_issues with the same filters, then tapps_linear_snapshot_put.
For a single-issue lookup, use mcp__plugin_linear_linear__get_issue(id=...) instead.
Or set TAPPS_LINEAR_SKIP_CACHE_GATE=1 for emergency bypass (logged).
See .claude/rules/linear-standards.md.
MSG
exit 2
"""
)

# TAP-1412: auto-populate the snapshot cache directly from the list_issues
# response. The agent forgetting to call tapps_linear_snapshot_put is the
# common failure mode that leaves .tapps-mcp-cache/linear-snapshots/ empty
# despite sentinels being written. This hook removes the human-in-the-loop
# step: it intercepts the PostToolUse for list_issues, computes the same key
# the snapshot tools use, extracts the issues array from tool_response, and
# writes the cache file directly. The cooperating server-side
# tapps_linear_snapshot_get reads it on the next call.
LINEAR_CACHE_GATE_POST_LIST_SCRIPT = """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook — Linear list_issues auto-populate (TAP-1412)
# After a successful mcp__plugin_linear_linear__list_issues call, write the
# response into .tapps-mcp-cache/linear-snapshots/<key>.json so the next
# tapps_linear_snapshot_get returns cached=true. Eliminates the manual
# snapshot_put step that was being skipped.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYBIN" ]; then
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
HOOK_ERR=$(echo "$INPUT" | TAPPS_PROJECT_ROOT="$ROOT" "$PYBIN" -c "
import sys, os, json, hashlib, time
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
name = d.get('tool_name') or d.get('toolName') or ''
if name not in __LINEAR_LIST_ISSUES_NAMES_REPR__:
    sys.exit(0)
inp = d.get('tool_input') or d.get('toolInput') or {}
team = (inp.get('team') or '').strip()
project = (inp.get('project') or '').strip()
state = (inp.get('state') or '').strip()
label = (inp.get('label') or '').strip()
try:
    limit = int(inp.get('limit') or 50)
except Exception:
    limit = 50
# Historically this hook required BOTH team and project and exited otherwise,
# so a team-only or project-only list_issues cached nothing — the cache stayed
# empty while the gate logged misses. The reader's _cache_key falls back to '_'
# for an empty segment exactly as this writer does, so every combination
# (including neither) produces a key the reader reproduces. No guard needed.
# TAP-4588: canonicalize the open-bucket alias and drop limit from the hash so
# this writer's key matches server _resolve_cache_key / the reader.
OPEN_BUCKET = ('backlog', 'unstarted', 'started', 'triage')
def _canon_state(s):
    s_lc = (s or '').strip().lower()
    if s_lc == '' or s_lc == 'open' or s_lc in OPEN_BUCKET:
        return 'open'
    return s_lc
canon = _canon_state(state)
filt = {k: v for k, v in sorted({
    'state': canon, 'label': label,
}.items()) if v not in (None, '')}
payload = json.dumps(filt, sort_keys=True, default=str).encode('utf-8')
fhash = hashlib.sha256(payload).hexdigest()[:16]
key = '__'.join([
    team.replace('/', '_') or '_',
    project.replace('/', '_') or '_',
    (canon.replace('/', '_') or 'any'),
    fhash,
])
# TAP-6581: refusals used to be a bare sys.exit(0) — the cache silently did
# not get written and nobody could tell a refusal from a no-op. Every refusal
# now names itself on stderr (the wrapper forwards only these marked lines) and
# appends a durable record, mirroring the .cache-gate-violations.jsonl channel.
root = os.environ.get('TAPPS_PROJECT_ROOT') or os.getcwd()
def _refuse(reason, rows):
    line = (
        'tapps-post-linear-list: refused cache write'
        ' reason=' + reason + ' key=' + key + ' rows=' + str(rows)
    )
    sys.stderr.write(line + chr(10))
    try:
        d2 = os.path.join(root, '.tapps-mcp')
        os.makedirs(d2, exist_ok=True)
        rec = {
            'ts': time.time(), 'key': key, 'reason': reason, 'rows': rows,
            'hook': 'tapps-post-linear-list',
        }
        with open(
            os.path.join(d2, '.linear-cache-write-refusals.jsonl'),
            'a', encoding='utf-8',
        ) as fh:
            fh.write(json.dumps(rec) + chr(10))
    except OSError:
        pass
    sys.exit(0)
resp = d.get('tool_response') or d.get('toolResponse') or {}
if isinstance(resp, str):
    try:
        resp = json.loads(resp)
    except Exception:
        resp = {}
def _as_json(s):
    # TAP-5901: MCP hosts deliver the payload as
    # {'content': [{'type': 'text', 'text': '{\"issues\": [...]}'}]} — the issue
    # list lives inside a nested JSON *string*. Walking dicts and lists alone
    # returns nothing there, and the empty result used to be cached.
    t = s.strip()
    if not t or t[0] not in '[{':
        return None
    try:
        return json.loads(t)
    except Exception:
        return None
def _find_issues(o):
    if isinstance(o, str):
        parsed = _as_json(o)
        return None if parsed is None else _find_issues(parsed)
    if isinstance(o, list):
        if o and isinstance(o[0], dict) and any(
            k in o[0] for k in ('identifier', 'id', 'title')
        ):
            return o
        for e in o:
            r = _find_issues(e)
            if r is not None:
                return r
        return None
    if isinstance(o, dict):
        if isinstance(o.get('issues'), list):
            return o['issues']
        for v in o.values():
            r = _find_issues(v)
            if r is not None:
                return r
    return None
# Store the COMPACT projection, mirroring server_linear_tools_keys._compact_issue.
# The raw plugin payload carries description/comments/attachments/history; a
# 50-issue backlog of that shape blows past the Read tool's 25 k-token ceiling,
# which is what forced agents into the fallback parse. Keep the fields triage
# actually reads and synthesize statusType so compact consumers see one shape.
COMPACT_FIELDS = (
    'id', 'identifier', 'title', 'state', 'status', 'statusType',
    'priority', 'estimate', 'assignee', 'parent',
)
def _compact(it):
    out = {k: v for k, v in it.items() if k in COMPACT_FIELDS}
    if 'statusType' not in out:
        st = out.get('state')
        if isinstance(st, dict) and st.get('type'):
            out['statusType'] = st['type']
        elif isinstance(out.get('status'), dict) and out['status'].get('type'):
            out['statusType'] = out['status']['type']
    return out
issues = [
    _compact(i) if isinstance(i, dict) else i for i in (_find_issues(resp) or [])
]
# Poisoning guard: never write an empty issue list. TAP-4588 only skipped the
# write when the raw request state was an alias/invalid, which required a
# truthy state — but the linear-read skill tells agents to OMIT state and
# filter in memory, so state was '' and an unparseable response cached zero
# issues under the canonical 'open' key for 30 minutes (TAP-5901). A miss costs
# one API call; a poisoned hit makes the agent report an empty backlog. Fail
# open: no write, and the next read repopulates.
state_lc = state.lower()
if not issues:
    _refuse('empty_issue_list', 0)
# TAP-6581 contents-level guard. The guard above tests the CONTAINER (is the
# list empty?); a list of one-field rows from list_issues(fields=['id']) sailed
# past it and was served for the whole 30-min open-bucket TTL as if it were a
# full projection. _COMPACT_FIELDS is the ceiling of a compact row; identity +
# title is the floor. A row below the floor is neither addressable nor
# readable, so refuse the WRITE rather than let the reader discover it later.
IDENTITY_FIELDS = ('identifier', 'id')
def _row_ok(it):
    if not isinstance(it, dict):
        return False
    return any(k in it for k in IDENTITY_FIELDS) and 'title' in it
if not all(_row_ok(i) for i in issues):
    _refuse('rows_below_compact_floor', len(issues))
# TTL aligned with server-side _ttl_for_state defaults (30 min open, 1 h closed).
# Keep in lockstep with Settings.linear_cache_ttl_open_seconds /
# linear_cache_ttl_closed_seconds — a writer that expires sooner than the reader
# expects silently reintroduces the empty-cache symptom.
ttl = 3600 if state_lc in ('completed', 'canceled') else 1800
now = time.time()
out = {
    'issues': issues,
    'cached_at': now,
    'expires_at': now + ttl,
    'state': state or None,
    'team': team,
    'project': project,
    'auto_populated': True,
    'limit': limit,
}
cache_dir = os.path.join(root, '.tapps-mcp-cache', 'linear-snapshots')
target = os.path.join(cache_dir, key + '.json')
# TAP-6581: a narrow fields= read must not DEGRADE a richer entry already
# cached under the same key. Richness = the fields guaranteed on EVERY row
# (their intersection); a strict subset of what is already stored is a
# downgrade and is refused. Equal or incomparable field sets still write, so
# a genuine refresh is never blocked.
def _guaranteed_fields(rows):
    covered = None
    for it in rows:
        if not isinstance(it, dict):
            return set()
        keys = set(it)
        covered = keys if covered is None else (covered & keys)
    return covered or set()
try:
    with open(target, encoding='utf-8') as fh:
        prior = json.load(fh)
except (OSError, ValueError):
    prior = None
if isinstance(prior, dict) and float(prior.get('expires_at') or 0) > time.time():
    prior_rows = prior.get('issues') or []
    if prior_rows:
        prior_fields = _guaranteed_fields(prior_rows)
        new_fields = _guaranteed_fields(issues)
        if new_fields < prior_fields:
            _refuse('would_degrade_cached_entry', len(issues))
try:
    os.makedirs(cache_dir, exist_ok=True)
    tmp = target + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(out, fh)
    os.replace(tmp, target)
    # Also drop a sentinel so a subsequent list_issues call passes the gate
    # without needing a snapshot_get round-trip first.
    sentinel_dir = os.path.join(root, '.tapps-mcp')
    os.makedirs(sentinel_dir, exist_ok=True)
    with open(os.path.join(sentinel_dir, '.linear-snapshot-sentinel-' + key), 'w') as fh:
        fh.write(str(int(now)))
except OSError:
    pass
" 2>&1 >/dev/null)
# TAP-6581: stderr was piped to /dev/null wholesale, so a refusal was
# indistinguishable from a successful write. Forward only our own marked lines
# (incidental interpreter noise stays suppressed, keeping the hook fail-open).
case "$HOOK_ERR" in
  *"tapps-post-linear-list: refused"*)
    printf '%s\n' "$HOOK_ERR" >&2
    ;;
esac
exit 0
"""

LINEAR_CACHE_GATE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "__LINEAR_LIST_ISSUES_MATCHER__",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-pre-linear-list.sh",
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "mcp__nlt-linear-issues__tapps_linear_snapshot_get",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-linear-snapshot-get.sh",
                },
            ],
        },
        {
            "matcher": "__LINEAR_LIST_ISSUES_MATCHER__",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-linear-list.sh",
                },
            ],
        },
    ],
}

LINEAR_CACHE_GATE_SCRIPTS: dict[str, str] = {
    "tapps-pre-linear-list.sh": LINEAR_CACHE_GATE_PRE_LIST_SCRIPT,
    "tapps-post-linear-snapshot-get.sh": LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT,
    "tapps-post-linear-list.sh": LINEAR_CACHE_GATE_POST_LIST_SCRIPT,
}

# PowerShell variants — same sentinel path, same key derivation rules.
LINEAR_CACHE_GATE_KEY_PS = """\
$inp = $null
if ($d.PSObject.Properties.Name -contains 'tool_input') { $inp = $d.tool_input }
elseif ($d.PSObject.Properties.Name -contains 'toolInput') { $inp = $d.toolInput }
$team = ''; $project = ''; $state = ''; $label = ''; $limit = 50
if ($inp) {
    if ($inp.PSObject.Properties.Name -contains 'team' -and $inp.team) { $team = [string]$inp.team }
    if ($inp.PSObject.Properties.Name -contains 'project' -and $inp.project) { $project = [string]$inp.project }
    if ($inp.PSObject.Properties.Name -contains 'state' -and $inp.state) { $state = [string]$inp.state }
    if ($inp.PSObject.Properties.Name -contains 'label' -and $inp.label) { $label = [string]$inp.label }
    if ($inp.PSObject.Properties.Name -contains 'limit' -and $inp.limit) {
        try { $limit = [int]$inp.limit } catch { $limit = 50 }
    }
}
$key = ''
if ($team -and $project) {
    # TAP-4588: canonicalize the open-bucket alias and drop limit from the hash
    # so the PowerShell key matches server _resolve_cache_key / the reader.
    $stateLc = $state.Trim().ToLower()
    $openBucket = @('backlog', 'unstarted', 'started', 'triage')
    if ($stateLc -eq '' -or $stateLc -eq 'open' -or $openBucket -contains $stateLc) {
        $canon = 'open'
    } else {
        $canon = $stateLc
    }
    $filtObj = [ordered]@{}
    if ($canon) { $filtObj['state'] = $canon }
    if ($label) { $filtObj['label'] = $label }
    $payload = ($filtObj | ConvertTo-Json -Compress)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLower().Substring(0, 16)
    $teamPart = if ($team) { $team.Replace('/', '_') } else { '_' }
    $projPart = if ($project) { $project.Replace('/', '_') } else { '_' }
    $statePart = if ($canon) { $canon.Replace('/', '_') } else { 'any' }
    $key = "${teamPart}__${projPart}__${statePart}__${hash}"
}
"""

LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT_PS = (
    """\
# TappsMCP PostToolUse hook — Linear cache-gate sentinel writer (TAP-1224)
$stdin = [Console]::In.ReadToEnd()
$tool = ''
try {
    $d = $stdin | ConvertFrom-Json
    if ($d.tool_name) { $tool = [string]$d.tool_name }
    elseif ($d.toolName) { $tool = [string]$d.toolName }
} catch { exit 0 }
if ($tool -ne 'mcp__tapps-mcp__tapps_linear_snapshot_get' -and $tool -ne 'mcp__nlt-linear-issues__tapps_linear_snapshot_get' -and $tool -ne 'tapps_linear_snapshot_get') {
    exit 0
}
"""
    + LINEAR_CACHE_GATE_KEY_PS
    + """\
if (-not $key) { exit 0 }
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
$dir = Join-Path $root '.tapps-mcp'
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$ts = [int64]([DateTimeOffset]::Now.ToUnixTimeSeconds())
Set-Content -Path (Join-Path $dir ".linear-snapshot-sentinel-${key}") -Value $ts -Encoding UTF8
exit 0
"""
)

LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS = (
    """\
# TappsMCP PreToolUse hook — Linear cache-first read gate (TAP-1224)
$mode = '__CACHE_GATE_MODE__'
$stdin = [Console]::In.ReadToEnd()
$tool = ''
try {
    $d = $stdin | ConvertFrom-Json
    if ($d.tool_name) { $tool = [string]$d.tool_name }
    elseif ($d.toolName) { $tool = [string]$d.toolName }
} catch { exit 0 }
if (-not (__LINEAR_LIST_ISSUES_PS_EQ__)) {
    exit 0
}
"""
    + LINEAR_CACHE_GATE_KEY_PS
    + """\
if (-not $key) { exit 0 }
"""
    + LEDGER_ROOT_RESOLVE_PS
    + """
$dir = Join-Path $root '.tapps-mcp'
if ($env:TAPPS_LINEAR_SKIP_CACHE_GATE -eq '1') {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $entry = @{ ts = (Get-Date -Format 'o'); bypass = 'TAPPS_LINEAR_SKIP_CACHE_GATE'; key = $key } | ConvertTo-Json -Compress
    Add-Content -Path (Join-Path $dir '.bypass-log.jsonl') -Value $entry
    exit 0
}
$sentinel = Join-Path $dir ".linear-snapshot-sentinel-${key}"
if (Test-Path $sentinel) {
    $now = [int64]([DateTimeOffset]::Now.ToUnixTimeSeconds())
    $sent = 0
    try { $sent = [int64](Get-Content $sentinel -Raw).Trim() } catch {}
    if ($sent -gt 0 -and ($now - $sent) -le 300) { exit 0 }
}
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$violation = @{ ts = (Get-Date -Format 'o'); key = $key; mode = $mode } | ConvertTo-Json -Compress
Add-Content -Path (Join-Path $dir '.cache-gate-violations.jsonl') -Value $violation
if ($mode -eq 'warn') {
    [Console]::Error.WriteLine("[TappsMCP refusal layer=hook-only/defense-in-depth] Primary gate is the tapps_linear_list_issues server tool (TAP-2008 Agent Gateway). This hook is the fallback layer - it fired because the raw Linear plugin was called directly instead of through the wrapper.")
    [Console]::Error.WriteLine("TappsMCP: Linear cache-first read rule (TAP-1224, warn mode) - no recent tapps_linear_snapshot_get for this slice.")
    [Console]::Error.WriteLine("Route reads through the linear-read skill. Allowed (warn) but logged to .tapps-mcp/.cache-gate-violations.jsonl.")
    [Console]::Error.WriteLine("See .claude/rules/linear-standards.md.")
    exit 0
}
[Console]::Error.WriteLine("[TappsMCP refusal layer=hook-only/defense-in-depth] Primary gate is the tapps_linear_list_issues server tool (TAP-2008 Agent Gateway). This hook is the fallback layer - it fired because the raw Linear plugin was called directly instead of through the wrapper.")
[Console]::Error.WriteLine("TappsMCP: Blocked mcp__plugin_linear_linear__list_issues - no recent tapps_linear_snapshot_get for this slice.")
[Console]::Error.WriteLine("Route reads through the linear-read skill (TAP-1260): tapps_linear_snapshot_get -> filter on hit, or list_issues + snapshot_put on miss.")
[Console]::Error.WriteLine("For a single-issue lookup, use get_issue. Bypass: TAPPS_LINEAR_SKIP_CACHE_GATE=1 (logged).")
[Console]::Error.WriteLine("See .claude/rules/linear-standards.md.")
exit 2
"""
)

LINEAR_CACHE_GATE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "__LINEAR_LIST_ISSUES_MATCHER__",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-linear-list.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "mcp__nlt-linear-issues__tapps_linear_snapshot_get",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-linear-snapshot-get.ps1"
                    ),
                },
            ],
        },
    ],
}

LINEAR_CACHE_GATE_SCRIPTS_PS: dict[str, str] = {
    "tapps-pre-linear-list.ps1": LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS,
    "tapps-post-linear-snapshot-get.ps1": LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT_PS,
}


# TAP-5452: bake known Linear MCP server ids into matchers + in-hook guards.
patch_linear_hook_matchers(LINEAR_CACHE_GATE_HOOKS_CONFIG)
patch_linear_hook_matchers(LINEAR_CACHE_GATE_HOOKS_CONFIG_PS)
LINEAR_CACHE_GATE_PRE_LIST_SCRIPT = apply_linear_host_placeholders(
    LINEAR_CACHE_GATE_PRE_LIST_SCRIPT
)
LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS = apply_linear_host_placeholders(
    LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS
)
LINEAR_CACHE_GATE_POST_LIST_SCRIPT = apply_linear_host_placeholders(
    LINEAR_CACHE_GATE_POST_LIST_SCRIPT
)
LINEAR_CACHE_GATE_SCRIPTS.update(resolve_linear_script_map(LINEAR_CACHE_GATE_SCRIPTS))
LINEAR_CACHE_GATE_SCRIPTS_PS.update(resolve_linear_script_map(LINEAR_CACHE_GATE_SCRIPTS_PS))


def render_cache_gate_scripts(
    mode: str,
    *,
    win: bool = False,
) -> dict[str, str]:
    """Return the cache-gate script set with ``__CACHE_GATE_MODE__`` baked in.

    Mode must be ``"warn"`` or ``"block"``. ``"off"`` should be handled by the
    caller (skip the install entirely) — passing it here renders a no-op safe
    "warn" variant so a stray render call cannot accidentally produce a block.
    """
    chosen = mode if mode in {"warn", "block"} else "warn"
    src = LINEAR_CACHE_GATE_SCRIPTS_PS if win else LINEAR_CACHE_GATE_SCRIPTS
    return {name: body.replace("__CACHE_GATE_MODE__", chosen) for name, body in src.items()}


# ---------------------------------------------------------------------------
# Session-start enforcement gate — opt-in via session_start_gate (off|warn|block)
# ---------------------------------------------------------------------------
#
# The SessionStart hook can only *prompt* the agent to call tapps_session_start;
# a hook cannot execute an MCP tool. When the agent ignores the prompt, every
# downstream quality tool runs in degraded mode. This gate makes the call
# enforceable:
#   * tapps-post-session-start.sh (PostToolUse) writes a per-Claude-session
#     ".session-start-done-<SID>" sentinel AFTER tapps_session_start actually
#     returns — proving the *tool* ran, not merely that the hook fired.
#   * tapps-pre-session-start-gate.sh (PreToolUse) blocks the TappsMCP quality
#     tool family until that tool-written sentinel exists for the current SID.
# session_start itself + cheap discovery/diagnostic tools are always allowed so
# the gate can never deadlock a fresh or broken session.

SESSION_START_GATE_POST_SCRIPT = """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook — session-start sentinel writer.
# Writes .session-start-done-<SID> AFTER tapps_session_start actually returns,
# proving the tool ran (not merely that the SessionStart hook fired). The
# pre-session-start gate reads this sentinel to release TappsMCP quality tools.
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -n1)
case "$TOOL" in
  *tapps_session_start) ;;
  *) exit 0 ;;
esac
SID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -n1)
[ -z "$SID" ] && exit 0
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
: > "$ROOT/.tapps-mcp/.session-start-done-$SID" 2>/dev/null
# Best-effort GC of sentinels left by prior Claude sessions (older than 1 day).
find "$ROOT/.tapps-mcp" -maxdepth 1 -name '.session-start-done-*' -mtime +1 -delete 2>/dev/null || true
exit 0
"""

SESSION_START_GATE_PRE_SCRIPT = (
    """\
#!/usr/bin/env bash
# TappsMCP PreToolUse hook — session-start enforcement gate.
# Blocks TappsMCP quality tools until tapps_session_start has actually run this
# Claude session (proven by a tool-written .session-start-done-<SID> sentinel,
# not merely the SessionStart hook firing). Mode is baked in at install time:
# "warn" logs to .session-start-gate-violations.jsonl and allows; "block"
# exits 2. Bypass with TAPPS_SKIP_SESSION_START_GATE=1 (logged to
# .tapps-mcp/.bypass-log.jsonl).
MODE="__SESSION_START_GATE_MODE__"
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -n1)
SID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -n1)
# Never gate session_start itself or cheap discovery/diagnostic tools — they
# establish the context or must stay reachable to repair a broken setup.
# tapps_memory is included: cross-session recall/handoff recovery (continue-session,
# the manual handoff fallback) has to work even when session_start has not run yet
# this session — that is exactly the broken-setup case this exemption exists for.
case "$TOOL" in
  *tapps_session_start|*tapps_server_info|*tapps_doctor|*tapps_usage|*tapps_stats|*tapps_memory) exit 0 ;;
esac
# Only gate the TappsMCP quality tool family (the matcher already scopes this;
# re-checked so a stray broad matcher can't over-block foreign tools).
case "$TOOL" in
  mcp__nlt-build__*|mcp__nlt-memory__*|mcp__nlt-setup__*|mcp__nlt-code-quality__*|mcp__nlt-platform-admin__*|mcp__tapps-mcp__*) ;;
  *) exit 0 ;;
esac
[ "$MODE" = "off" ] && exit 0
"""
    + LEDGER_ROOT_RESOLVE_BASH
    + """
if [ "${TAPPS_SKIP_SESSION_START_GATE:-0}" = "1" ]; then
  mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
  echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"bypass\\":\\"TAPPS_SKIP_SESSION_START_GATE\\",\\"tool\\":\\"${TOOL}\\"}" \\
    >> "$ROOT/.tapps-mcp/.bypass-log.jsonl" 2>/dev/null
  exit 0
fi
# Unidentifiable session — cannot prove state; fail open rather than deadlock.
if [ -z "$SID" ]; then
  exit 0
fi
if [ -f "$ROOT/.tapps-mcp/.session-start-done-$SID" ]; then
  exit 0
fi
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"tool\\":\\"${TOOL}\\",\\"mode\\":\\"${MODE}\\",\\"sid\\":\\"${SID}\\"}" \\
  >> "$ROOT/.tapps-mcp/.session-start-gate-violations.jsonl" 2>/dev/null
if [ "$MODE" = "warn" ]; then
  cat >&2 <<MSG
[TappsMCP refusal layer=hook-only/defense-in-depth] session-start gate (warn) — ${TOOL} was called before tapps_session_start ran this session.
Call tapps_session_start() first: it bootstraps project context, the checker matrix, and brain auth. Without it, quality verdicts are degraded.
This call is allowed (warn mode) but logged to .tapps-mcp/.session-start-gate-violations.jsonl.
MSG
  exit 0
fi
cat >&2 <<MSG
[TappsMCP refusal layer=hook-only/defense-in-depth] session-start gate (block) — ${TOOL} was called before tapps_session_start ran this session.
Call tapps_session_start() NOW, then retry: it bootstraps project context, the checker matrix, and brain auth. TappsMCP tools run degraded without it.
Emergency bypass: TAPPS_SKIP_SESSION_START_GATE=1 (logged to .tapps-mcp/.bypass-log.jsonl).
MSG
exit 2
"""
)

SESSION_START_GATE_SCRIPTS: dict[str, str] = {
    "tapps-pre-session-start-gate.sh": SESSION_START_GATE_PRE_SCRIPT,
    "tapps-post-session-start.sh": SESSION_START_GATE_POST_SCRIPT,
}

SESSION_START_GATE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "mcp__(nlt-build|nlt-memory|nlt-setup|nlt-code-quality|nlt-platform-admin|tapps-mcp)__.*",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-pre-session-start-gate.sh",
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "mcp__.*__tapps_session_start",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-session-start.sh",
                },
            ],
        },
    ],
}

SESSION_START_GATE_POST_SCRIPT_PS = """\
# TappsMCP PostToolUse hook — session-start sentinel writer.
$stdin = [Console]::In.ReadToEnd()
$tool = ''; $sid = ''
try {
    $d = $stdin | ConvertFrom-Json
    if ($d.tool_name) { $tool = [string]$d.tool_name }
    elseif ($d.toolName) { $tool = [string]$d.toolName }
    if ($d.session_id) { $sid = [string]$d.session_id }
    elseif ($d.sessionId) { $sid = [string]$d.sessionId }
} catch { exit 0 }
if ($tool -notmatch 'tapps_session_start$') { exit 0 }
if (-not $sid) { exit 0 }
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
$dir = Join-Path $root '.tapps-mcp'
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
Set-Content -Path (Join-Path $dir ".session-start-done-${sid}") -Value '' -Encoding UTF8
Get-ChildItem -Path $dir -Filter '.session-start-done-*' -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
exit 0
"""

SESSION_START_GATE_PRE_SCRIPT_PS = (
    """\
# TappsMCP PreToolUse hook — session-start enforcement gate.
$mode = '__SESSION_START_GATE_MODE__'
$stdin = [Console]::In.ReadToEnd()
$tool = ''; $sid = ''
try {
    $d = $stdin | ConvertFrom-Json
    if ($d.tool_name) { $tool = [string]$d.tool_name }
    elseif ($d.toolName) { $tool = [string]$d.toolName }
    if ($d.session_id) { $sid = [string]$d.session_id }
    elseif ($d.sessionId) { $sid = [string]$d.sessionId }
} catch { exit 0 }
if ($tool -match 'tapps_(session_start|server_info|doctor|usage|stats|memory)$') { exit 0 }
if ($tool -notmatch '^mcp__(nlt-build|nlt-memory|nlt-setup|nlt-code-quality|nlt-platform-admin|tapps-mcp)__') { exit 0 }
if ($mode -eq 'off') { exit 0 }
"""
    + LEDGER_ROOT_RESOLVE_PS
    + """
$dir = Join-Path $root '.tapps-mcp'
if ($env:TAPPS_SKIP_SESSION_START_GATE -eq '1') {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Add-Content -Path (Join-Path $dir '.bypass-log.jsonl') -Value ("{`"ts`":`"" + (Get-Date -Format o) + "`",`"bypass`":`"TAPPS_SKIP_SESSION_START_GATE`",`"tool`":`"$tool`"}")
    exit 0
}
if (-not $sid) { exit 0 }
if (Test-Path (Join-Path $dir ".session-start-done-${sid}")) { exit 0 }
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
Add-Content -Path (Join-Path $dir '.session-start-gate-violations.jsonl') -Value ("{`"ts`":`"" + (Get-Date -Format o) + "`",`"tool`":`"$tool`",`"mode`":`"$mode`",`"sid`":`"$sid`"}")
if ($mode -eq 'warn') {
    [Console]::Error.WriteLine("[TappsMCP refusal layer=hook-only/defense-in-depth] session-start gate (warn) — $tool called before tapps_session_start ran this session. Call tapps_session_start() first (logged to .session-start-gate-violations.jsonl).")
    exit 0
}
[Console]::Error.WriteLine("[TappsMCP refusal layer=hook-only/defense-in-depth] session-start gate (block) — $tool called before tapps_session_start ran this session. Call tapps_session_start() NOW, then retry. Bypass: TAPPS_SKIP_SESSION_START_GATE=1.")
exit 2
"""
)

SESSION_START_GATE_SCRIPTS_PS: dict[str, str] = {
    "tapps-pre-session-start-gate.ps1": SESSION_START_GATE_PRE_SCRIPT_PS,
    "tapps-post-session-start.ps1": SESSION_START_GATE_POST_SCRIPT_PS,
}

SESSION_START_GATE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "mcp__(nlt-build|nlt-memory|nlt-setup|nlt-code-quality|nlt-platform-admin|tapps-mcp)__.*",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-session-start-gate.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "mcp__.*__tapps_session_start",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-session-start.ps1"
                    ),
                },
            ],
        },
    ],
}


def render_session_start_gate_scripts(
    mode: str,
    *,
    win: bool = False,
) -> dict[str, str]:
    """Return the session-start gate script set with the mode baked in.

    ``mode`` must be ``"warn"`` or ``"block"``. ``"off"`` should be handled by
    the caller (skip the install entirely); passing it here renders a safe
    ``"warn"`` variant so a stray render call cannot accidentally produce a
    block. Only the PreToolUse gate carries the ``__SESSION_START_GATE_MODE__``
    placeholder; the sentinel writer is mode-independent.
    """
    chosen = mode if mode in {"warn", "block"} else "warn"
    src = SESSION_START_GATE_SCRIPTS_PS if win else SESSION_START_GATE_SCRIPTS
    return {name: body.replace("__SESSION_START_GATE_MODE__", chosen) for name, body in src.items()}
