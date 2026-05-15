"""Hook script templates and configuration for Claude Code and Cursor.

Contains all shell/PowerShell hook script strings and their JSON config
mappings. Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Claude Code hook script templates (Story 12.5)
# ---------------------------------------------------------------------------

CLAUDE_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-session-start.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionStart hook (startup/resume)
# Directs the agent to call tapps_session_start as the first MCP action.
# TAP-1379: Short-circuits on subsequent fires within the same Claude session
# (resume/compact re-fire the SessionStart hook; emitting the REQUIRED prompt
# every time caused agents to re-call tapps_session_start ~23x per session).
INPUT=$(cat)
SID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -n1)
SENTINEL_DIR="${TAPPS_PROJECT_ROOT:-.}/.tapps-mcp"
if [ -n "$SID" ]; then
  SENTINEL="$SENTINEL_DIR/.session-start-fired-$SID"
  if [ -f "$SENTINEL" ]; then
    # Already prompted the agent for this Claude session; stay silent on resume.
    exit 0
  fi
  mkdir -p "$SENTINEL_DIR" 2>/dev/null || true
  : > "$SENTINEL" 2>/dev/null || true
fi
echo "REQUIRED: Call tapps_session_start() NOW as your first action."
echo "This initializes project context for all TappsMCP quality tools."
echo "Tools called without session_start will have degraded accuracy."
exit 0
""",
    "tapps-session-compact.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionStart hook (compact)
# Re-injects TappsMCP context after context compaction.
INPUT=$(cat)
echo "[TappsMCP] Context was compacted — re-injecting TappsMCP awareness."
echo "Remember: use tapps_quick_check after editing Python files."
echo "Run tapps_validate_changed before declaring work complete."
exit 0
""",
    "tapps-post-edit.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook (Edit/Write) — TAP-1326 / TAP-1330
# Records edited gate-tracked files to .ralph/.edits_this_loop and detects
# new external imports requiring tapps_lookup_docs. Advisory only here; the
# Stop hook enforces the gate.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
PARSED=$(TAPPS_HOOK_INPUT="$INPUT" "$PYBIN" - <<'PYEOF' 2>/dev/null
import os, json, re
try:
    d = json.loads(os.environ.get('TAPPS_HOOK_INPUT', '{}'))
    ti = d.get('tool_input') or d.get('toolInput') or {}
    f = ti.get('file_path') or ti.get('path') or ''
    content = ti.get('content') or ti.get('new_string') or ''
    print(f)
    libs = set()
    if f.endswith(('.py', '.pyi')):
        for m in re.finditer(r'^\\s*(?:from|import)\\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.M):
            libs.add(m.group(1))
    elif f.endswith(('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')):
        for m in re.finditer(r'''^\\s*import[^'"]*['"]([^'"./][^'"]*)['"]''', content, re.M):
            libs.add(m.group(1).split('/')[0])
    print(','.join(sorted(libs)))
except Exception:
    print('')
    print('')
PYEOF
)
FILE=$(echo "$PARSED" | sed -n '1p')
LIBS=$(echo "$PARSED" | sed -n '2p')
case "$FILE" in
  *.py|*.pyi|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs)
    ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
    mkdir -p "$ROOT/.ralph" 2>/dev/null
    LOOP_FILE="$ROOT/.ralph/.edits_this_loop"
    touch "$LOOP_FILE"
    if ! grep -Fxq "$FILE" "$LOOP_FILE" 2>/dev/null; then
      echo "$FILE" >> "$LOOP_FILE"
    fi
    echo "Edited: $FILE — run tapps_quick_check before EXIT_SIGNAL." >&2
    if [ -n "$LIBS" ]; then
      echo "New imports detected ($LIBS) — call tapps_lookup_docs(library=...) before declaring complete (TAP-1330)." >&2
    fi
    ;;
esac
exit 0
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook — TAP-1326 / TAP-1327
# Enforces tapps_quick_check / validate_changed / quality_gate after file
# edits and tapps_checklist before EXIT_SIGNAL. Overrides Ralph status.json
# EXIT_SIGNAL=true → false on miss; logs to .ralph/logs/on-stop.log.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
PARSED=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('stop_hook_active','false'))
    print(d.get('transcript_path',''))
except Exception:
    print('false'); print('')" 2>/dev/null)
ACTIVE=$(echo "$PARSED" | sed -n '1p')
TRANSCRIPT=$(echo "$PARSED" | sed -n '2p')
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATUS_JSON="$PROJECT_DIR/.ralph/status.json"
EDITS_FILE="$PROJECT_DIR/.ralph/.edits_this_loop"
LOG_DIR="$PROJECT_DIR/.ralph/logs"
PROMPT_FILE="$PROJECT_DIR/.ralph/PROMPT.md"
# EXIT_SIGNAL gate (Ralph projects only — no-op if status.json absent).
if [ -f "$STATUS_JSON" ]; then
  EXIT_SIGNAL=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$STATUS_JSON'))
    print('true' if d.get('EXIT_SIGNAL') is True or str(d.get('EXIT_SIGNAL','')).lower()=='true' else 'false')
except Exception:
    print('false')" 2>/dev/null)
  if [ "$EXIT_SIGNAL" = "true" ] && [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    GATE_REPORT=$("$PYBIN" - <<PYEOF 2>/dev/null
import json,os,time
transcript='$TRANSCRIPT'
edits_file='$EDITS_FILE'
project_dir='$PROJECT_DIR'
gate_tools={'tapps_quick_check','tapps_validate_changed','tapps_quality_gate',
            'mcp__tapps-mcp__tapps_quick_check','mcp__tapps-mcp__tapps_validate_changed',
            'mcp__tapps-mcp__tapps_quality_gate','mcp__tapps-quality__tapps_quick_check',
            'mcp__tapps-quality__tapps_validate_changed','mcp__tapps-quality__tapps_quality_gate'}
checklist_tools={'tapps_checklist','mcp__tapps-mcp__tapps_checklist','mcp__tapps-quality__tapps_checklist'}
lookup_tools={'tapps_lookup_docs','mcp__tapps-mcp__tapps_lookup_docs','mcp__tapps-quality__tapps_lookup_docs'}
mcp_calls=0
gate_called=False
checklist_called=False
lookup_called=False
tools_used=set()
try:
    with open(transcript) as fh:
        for line in fh:
            try: row=json.loads(line)
            except Exception: continue
            msg=row.get('message') or {}
            for blk in (msg.get('content') or []):
                if not isinstance(blk,dict): continue
                if blk.get('type')!='tool_use': continue
                name=blk.get('name','')
                tools_used.add(name)
                if name.startswith('mcp__'): mcp_calls+=1
                if name in gate_tools: gate_called=True
                if name in checklist_tools: checklist_called=True
                if name in lookup_tools: lookup_called=True
except Exception:
    pass
edits=[]
if os.path.exists(edits_file):
    with open(edits_file) as fh:
        edits=[ln.strip() for ln in fh if ln.strip()]
needs_gate=any(p.endswith(('.py','.pyi','.ts','.tsx','.js','.jsx','.go','.rs')) for p in edits)
miss=[]
gate_skipped=[]
if needs_gate and not gate_called:
    miss.append('QUALITY_GATE_SKIP:'+','.join(edits[:8]))
    gate_skipped=edits
if not checklist_called:
    miss.append('CHECKLIST_MISSING')
# TAP-1333: append per-loop telemetry (rotates at 10 MB).
try:
    metrics_dir=os.path.join(project_dir,'.tapps-mcp')
    os.makedirs(metrics_dir,exist_ok=True)
    metrics_path=os.path.join(metrics_dir,'loop-metrics.jsonl')
    if os.path.exists(metrics_path) and os.path.getsize(metrics_path) > 10*1024*1024:
        os.replace(metrics_path, metrics_path + '.1')
    with open(metrics_path,'a') as fh:
        fh.write(json.dumps({
            'ts': int(time.time()),
            'files_edited': edits,
            'mcp_calls': mcp_calls,
            'gate_skipped_files': gate_skipped,
            'lookup_docs_called': lookup_called,
            'checklist_called': checklist_called,
            'tools_used': sorted(tools_used)[:50],
        }) + '\\n')
except Exception:
    pass
print('|'.join(miss))
PYEOF
)
    if [ -n "$GATE_REPORT" ]; then
      mkdir -p "$LOG_DIR" 2>/dev/null
      TS=$(date -u +%FT%TZ)
      echo "{\\"ts\\":\\"$TS\\",\\"override\\":\\"EXIT_SIGNAL\\",\\"reasons\\":\\"$GATE_REPORT\\"}" \\
        >> "$LOG_DIR/on-stop.log" 2>/dev/null
      "$PYBIN" - <<PYEOF 2>/dev/null
import json
try:
    p='$STATUS_JSON'
    d=json.load(open(p))
    d['EXIT_SIGNAL']=False
    d['exit_signal_override']='$GATE_REPORT'
    json.dump(d,open(p,'w'),indent=2)
except Exception:
    pass
PYEOF
      if [ -f "$PROMPT_FILE" ]; then
        {
          echo ""
          echo "<!-- TappsMCP override $TS: EXIT_SIGNAL forced false. Run missing gates next loop: $GATE_REPORT -->"
        } >> "$PROMPT_FILE" 2>/dev/null
      fi
      cat >&2 <<MSG
TappsMCP: EXIT_SIGNAL=true overridden to false — required gates skipped:
  $GATE_REPORT
Run tapps_quick_check / tapps_validate_changed and tapps_checklist before retrying.
See .claude/rules/tapps-pipeline.md.
MSG
    fi
  fi
  # Reset edits_this_loop after Stop processes it.
  : > "$EDITS_FILE" 2>/dev/null
fi
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
if [ -f "$PROGRESS" ]; then
  SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
except Exception:
    pass
" 2>/dev/null)
  if [ -n "$SUMMARY" ]; then
    echo "$SUMMARY" >&2
    exit 0
  fi
fi
# Check report sidecar
REPORT_PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
if [ -f "$REPORT_PROGRESS" ]; then
  REPORT_SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$REPORT_PROGRESS'))
    if d.get('status')=='completed':
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'Last report: {len(results)} files, avg {avg:.1f}/100')
except Exception:
    pass
" 2>/dev/null)
  [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
fi
echo "Reminder: Before declaring complete, run /tapps-finish-task (or tapps_validate_changed + tapps_checklist manually)." >&2
exit 0
""",
    "tapps-user-prompt-submit.sh": """\
#!/usr/bin/env bash
# TappsMCP UserPromptSubmit hook (TAP-975)
# Re-surfaces pipeline state per user turn so long sessions don't drift.
# Reads two sidecars:
#   .tapps-mcp/.session-start-marker   — Unix epoch of last tapps_session_start
#   .tapps-mcp/.checklist-state.json   — last tapps_checklist outcome
# Stays SILENT when session_start was within 30 min AND no open checklist.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
SS_MARKER="$PROJECT_DIR/.tapps-mcp/.session-start-marker"
CL_STATE="$PROJECT_DIR/.tapps-mcp/.checklist-state.json"
NOW=$(date +%s)
NEED_SS=0
if [ ! -f "$SS_MARKER" ]; then
  NEED_SS=1
else
  SS=$(cat "$SS_MARKER" 2>/dev/null)
  if ! echo "$SS" | grep -Eq '^[0-9]+$'; then
    SS=0
  fi
  AGE=$((NOW - SS))
  # 1800s = 30 minute freshness window per TAP-975 AC.
  if [ "$AGE" -gt 1800 ]; then
    NEED_SS=1
  fi
fi
OPEN_CHECKLIST=""
if [ -f "$CL_STATE" ]; then
  PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  OPEN_CHECKLIST=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$CL_STATE'))
    if d.get('complete') is False:
        m=d.get('missing_required',[])
        if m:
            print('open: ' + ', '.join(m[:3]))
        else:
            print('open')
except Exception:
    pass
" 2>/dev/null)
fi
if [ "$NEED_SS" -eq 0 ] && [ -z "$OPEN_CHECKLIST" ]; then
  exit 0
fi
{
  echo "[TappsMCP] Pipeline-state reminder:"
  if [ "$NEED_SS" -eq 1 ]; then
    echo "  - tapps_session_start was not called within the last 30 min — call it before edits to refresh project context."
  fi
  if [ -n "$OPEN_CHECKLIST" ]; then
    echo "  - tapps_checklist last reported incomplete ($OPEN_CHECKLIST) — run /tapps-finish-task or address the missing tools."
  fi
} >&2
exit 0
""",
    "tapps-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
# Reads sidecar progress file for richer context when available.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -f "$PROGRESS" ]; then
  SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
except Exception:
    pass
" 2>/dev/null)
  if [ -n "$SUMMARY" ]; then
    echo "$SUMMARY" >&2
    exit 0
  fi
fi
# Check report sidecar
REPORT_PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
if [ -f "$REPORT_PROGRESS" ]; then
  REPORT_SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$REPORT_PROGRESS'))
    if d.get('status')=='completed':
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'Last report: {len(results)} files, avg {avg:.1f}/100')
except Exception:
    pass
" 2>/dev/null)
  [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
fi
MSG="Reminder: run tapps_validate_changed to confirm quality."
echo "$MSG" >&2
exit 0
""",
    "tapps-post-validate.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook (tapps_validate_changed)
# Reads the sidecar progress file and echoes a summary to the transcript.
# This provides a second delivery path for validation results.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
if [ -f "$PROGRESS" ]; then
  PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  SUMMARY=$("$PYBIN" -c "
import json,sys
try:
    d=json.load(open('$PROGRESS'))
    status=d.get('status','unknown')
    if status=='completed':
        total=d.get('total',0)
        passed=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        failed=total-passed
        ms=d.get('elapsed_ms',0)
        sec=ms/1000.0
        gp='ALL PASSED' if d.get('all_gates_passed') else f'{failed} FAILED'
        print(f'[TappsMCP] Validation: {total} files, {gp} ({sec:.1f}s)')
    elif status=='error':
        print(f'[TappsMCP] Validation error: {d.get(\"error\",\"unknown\")}')
    elif status=='running':
        done=d.get('completed',0)
        total=d.get('total',0)
        print(f'[TappsMCP] Validation in progress: {done}/{total} files')
except Exception:
    pass
" 2>/dev/null)
  if [ -n "$SUMMARY" ]; then
    echo "$SUMMARY"
  fi
fi
exit 0
""",
    "tapps-post-report.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook (tapps_report)
# Reads the report sidecar progress file and echoes a summary.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
if [ -f "$PROGRESS" ]; then
  PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  SUMMARY=$("$PYBIN" -c "
import json,sys
try:
    d=json.load(open('$PROGRESS'))
    status=d.get('status','unknown')
    if status=='completed':
        total=d.get('total',0)
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'[TappsMCP] Report: {total} files scored, avg {avg:.1f}/100')
        else:
            print(f'[TappsMCP] Report: {total} files scored')
    elif status=='error':
        print(f'[TappsMCP] Report error: {d.get(\"error\",\"unknown\")}')
    elif status=='running':
        done=d.get('completed',0)
        total=d.get('total',0)
        print(f'[TappsMCP] Report in progress: {done}/{total} files')
except Exception:
    pass
" 2>/dev/null)
  [ -n "$SUMMARY" ] && echo "$SUMMARY"
fi
exit 0
""",
    "tapps-pre-compact.sh": """\
#!/usr/bin/env bash
# TappsMCP PreCompact hook
# Backs up scoring context before context window compaction.
INPUT=$(cat)
BACKUP_DIR="${CLAUDE_PROJECT_DIR:-.}/.tapps-mcp"
mkdir -p "$BACKUP_DIR"
echo "$INPUT" > "$BACKUP_DIR/pre-compact-context.json"
echo "[TappsMCP] Scoring context backed up to $BACKUP_DIR/pre-compact-context.json"
exit 0
""",
    "tapps-subagent-start.sh": """\
#!/usr/bin/env bash
# TappsMCP SubagentStart hook
# Injects TappsMCP awareness into spawned subagents.
INPUT=$(cat)
echo "[TappsMCP] This project uses TappsMCP for code quality."
echo "MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed, tapps_memory."
exit 0
""",
    "tapps-subagent-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP SubagentStop hook (Epic 36.1)
# Advises on quality validation when subagent modified Python files.
# IMPORTANT: SubagentStop does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
# Check for Python file modifications (best-effort)
HAS_PY=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
try:
    d=json.load(sys.stdin)
    # SubagentStop event may include changed files info
    print('yes')
except Exception:
    print('no')
" 2>/dev/null)
if [ "$HAS_PY" = "yes" ]; then
  echo "Subagent completed. Run tapps_quick_check or tapps_validate_changed" >&2
  echo "on any Python files modified by this subagent." >&2
fi
exit 0
""",
    "tapps-session-end.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionEnd hook (Epic 36.2)
# Creates a quality summary at session end.
# IMPORTANT: SessionEnd does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
if [ -f "$MARKER" ]; then
  echo "[TappsMCP] Session quality validated." >&2
else
  echo "[TappsMCP] Session ended without running quality validation." >&2
  echo "Consider running tapps_validate_changed before ending sessions." >&2
fi
exit 0
""",
    "tapps-tool-failure.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUseFailure hook (Epic 36.3 / TAP-976)
# Logs TappsMCP MCP tool failures for diagnostics.
# IMPORTANT: PostToolUseFailure does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
TOOL=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('tool_name',''))
" 2>/dev/null)
# Only log failures from TappsMCP tools — non-tapps failures stay silent.
case "$TOOL" in
  mcp__tapps-mcp__*|mcp__tapps_mcp__*) ;;
  *) exit 0 ;;
esac
ERROR=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
d=json.load(sys.stdin)
print(str(d.get('error','unknown error'))[:200])
" 2>/dev/null)
echo "TappsMCP tool $TOOL failed: $ERROR" >&2
echo "Run tapps_doctor to diagnose, or check MCP server connectivity." >&2
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
TS=$(date -u +%FT%TZ)
LINE=$(echo "$INPUT" | TS="$TS" TOOL="$TOOL" ERROR="$ERROR" "$PYBIN" -c "
import json, os, sys
print(json.dumps({
    'ts': os.environ.get('TS', ''),
    'tool': os.environ.get('TOOL', ''),
    'error': os.environ.get('ERROR', ''),
}, separators=(',', ':')))
" 2>/dev/null)
if [ -n "$LINE" ]; then
  echo "$LINE" >> "$ROOT/.tapps-mcp/.failure-log.jsonl" 2>/dev/null
fi
exit 0
""",
    "tapps-pre-bash.sh": """\
#!/usr/bin/env bash
# TappsMCP PreToolUse hook (Bash) - destructive command guard (opt-in)
# Blocks commands containing rm -rf, format c:, etc. Exit 2 = block, 0 = allow.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYBIN" ]; then
  # TAP-1785: enforcement gate fails closed when python is unavailable.
  ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
  mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
  echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"hook\\":\\"tapps-pre-bash\\",\\"reason\\":\\"no_python\\"}" \\
    >> "$ROOT/.tapps-mcp/.bypass-log.jsonl" 2>/dev/null
  echo "TappsMCP: Blocked — no python interpreter available to evaluate destructive-command guard." >&2
  exit 2
fi
CMD=$(echo "$INPUT" | "$PYBIN" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {}) or {}
    cmd = ti.get('command', '') or ti.get('cmd', '')
    if not cmd and isinstance(ti.get('args'), list):
        cmd = ' '.join(str(a) for a in ti['args'])
    print(cmd if isinstance(cmd, str) else '')
except Exception:
    print('')
" 2>/dev/null)
# Blocklist (substring match, case-insensitive for format/del).
# Fork-bomb signature ":(){"  is matched as a QUOTED literal substring
# because bare ( / ) terminate case alternatives early and cause a bash
# syntax error. The substring ":(){" is distinctive enough on its own.
BLOCK=0
case "$CMD" in
  *rm\\ -rf*|*rm\\ -fr*|*rm\\ -r\\ -f*|*rm\\ -rf\\ /*) BLOCK=1 ;;
  *format\\ c:*|*format\\ c:/*|*format\\ C:*|*format\\ C:/*) BLOCK=1 ;;
  *del\\ /f\\ /s\\ /q*|*del\\ /s\\ /q*|*rd\\ /s\\ /q*) BLOCK=1 ;;
  *":(){"*) BLOCK=1 ;;
esac
if [ "$BLOCK" = 1 ]; then
  echo "TappsMCP: Blocked potentially destructive command." >&2
  exit 2
fi
exit 0
""",
    "tapps-memory-auto-capture.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook - Auto-Capture (Epic 65.5)
# Extracts durable facts from context and saves via tapps_memory save_bulk.
# Runs tapps-mcp auto-capture with stdin; configurable max_facts, min_context.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))" \
  2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
if command -v tapps-mcp >/dev/null 2>&1; then
  echo "$INPUT" | tapps-mcp auto-capture --project-root "$PROJECT_DIR" 2>/dev/null || true
elif [ -n "$PYBIN" ]; then
  echo "$INPUT" | "$PYBIN" -m tapps_mcp.cli auto-capture --project-root "$PROJECT_DIR" 2>/dev/null || true
fi
exit 0
""",
    "tapps-memory-capture.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook - Memory Capture (Epic 34.5)
# Writes session quality data to .tapps-mcp/session-capture.json for
# persistence into shared memory on next session start.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))" \
  2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CAPTURE_DIR="$PROJECT_DIR/.tapps-mcp"
MARKER="$CAPTURE_DIR/.validation-marker"
VALIDATED="false"
if [ -f "$MARKER" ]; then
  VALIDATED="true"
fi
DATE=$("$PYBIN" -c "from datetime import date; print(date.today().isoformat())" 2>/dev/null \
  || date +%Y-%m-%d 2>/dev/null || echo "unknown")
FILES=$("$PYBIN" -c \
  "import subprocess,sys;r=subprocess.run(['git','diff','--name-only','HEAD'],capture_output=True,text=True,cwd='$PROJECT_DIR');print(len([f for f in r.stdout.strip().split(chr(10)) if f.endswith('.py') and f]))" \
  2>/dev/null || echo "0")
mkdir -p "$CAPTURE_DIR" 2>/dev/null || exit 0
"$PYBIN" -c "
import json,sys
data={'date':'$DATE','validated':$VALIDATED,'files_edited':int('$FILES' or '0')}
with open('$CAPTURE_DIR/session-capture.json','w') as f:
    json.dump(data,f)
" 2>/dev/null
exit 0
""",
}

# ---------------------------------------------------------------------------
# Claude Code hook script templates - PowerShell (Windows)
# ---------------------------------------------------------------------------

CLAUDE_HOOK_SCRIPTS_PS: dict[str, str] = {
    "tapps-session-start.ps1": """\
# TappsMCP SessionStart hook (startup/resume)
# Directs the agent to call tapps_session_start as the first MCP action.
$null = $input | Out-Null
Write-Output "REQUIRED: Call tapps_session_start() NOW as your first action."
Write-Output "This initializes project context for all TappsMCP quality tools."
Write-Output "Tools called without session_start will have degraded accuracy."
exit 0
""",
    "tapps-session-compact.ps1": """\
# TappsMCP SessionStart hook (compact)
# Re-injects TappsMCP context after context compaction.
$null = $input | Out-Null
Write-Output "[TappsMCP] Context was compacted - re-injecting TappsMCP awareness."
Write-Output "Remember: use tapps_quick_check after editing Python files."
Write-Output "Run tapps_validate_changed before declaring work complete."
exit 0
""",
    "tapps-post-edit.ps1": """\
# TappsMCP PostToolUse hook (Edit/Write)
# Reminds the agent to run quality checks after file edits.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $file = if ($data.tool_input.file_path) { $data.tool_input.file_path }
            elseif ($data.tool_input.path) { $data.tool_input.path }
            else { "" }
} catch {
    $file = ""
}
if ($file -and $file -match '\\.py$') {
    Write-Output "Python file edited: $file"
    Write-Output "Consider running tapps_quick_check on it."
}
exit 0
""",
    "tapps-stop.ps1": """\
# TappsMCP Stop hook
# Reminds to run tapps_validate_changed but does NOT block.
# Reads sidecar progress file for richer context when available.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
            Write-Host "Last validation: $total files, $gp" -ForegroundColor Cyan
            exit 0
        }
    } catch {}
}
# Check report sidecar
$reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $reportProgress) {
    try {
        $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
        if ($rd.status -eq "completed") {
            $results = @($rd.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "Last report: $($results.Count) files, avg $avg/100"
            }
        }
    } catch {}
}
Write-Host "Reminder: Before declaring complete, run /tapps-finish-task (or tapps_validate_changed + tapps_checklist manually)." -ForegroundColor Yellow
exit 0
""",
    "tapps-user-prompt-submit.ps1": """\
# TappsMCP UserPromptSubmit hook (TAP-975)
# Re-surfaces pipeline state per user turn so long sessions don't drift.
# Reads two sidecars:
#   .tapps-mcp/.session-start-marker   — Unix epoch of last tapps_session_start
#   .tapps-mcp/.checklist-state.json   — last tapps_checklist outcome
# Stays SILENT when session_start was within 30 min AND no open checklist.
$null = $input | Out-Null
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$ssMarker = Join-Path $projDir '.tapps-mcp/.session-start-marker'
$clState = Join-Path $projDir '.tapps-mcp/.checklist-state.json'
$now = [int64]([DateTimeOffset]::Now.ToUnixTimeSeconds())
$needSs = $false
if (-not (Test-Path $ssMarker)) {
    $needSs = $true
} else {
    $raw = ''
    try { $raw = (Get-Content -Path $ssMarker -Raw -ErrorAction Stop).Trim() } catch {}
    if ($raw -notmatch '^[0-9]+$') {
        $needSs = $true
    } else {
        $age = $now - [int64]$raw
        if ($age -gt 1800) { $needSs = $true }
    }
}
$openChecklist = ''
if (Test-Path $clState) {
    try {
        $d = Get-Content -Path $clState -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($d.complete -eq $false) {
            $missing = @($d.missing_required)
            if ($missing.Count -gt 0) {
                $first = ($missing | Select-Object -First 3) -join ', '
                $openChecklist = "open: $first"
            } else {
                $openChecklist = 'open'
            }
        }
    } catch {}
}
if (-not $needSs -and -not $openChecklist) {
    exit 0
}
[Console]::Error.WriteLine('[TappsMCP] Pipeline-state reminder:')
if ($needSs) {
    [Console]::Error.WriteLine('  - tapps_session_start was not called within the last 30 min - call it before edits to refresh project context.')
}
if ($openChecklist) {
    [Console]::Error.WriteLine("  - tapps_checklist last reported incomplete ($openChecklist) - run /tapps-finish-task or address the missing tools.")
}
exit 0
""",
    "tapps-task-completed.ps1": """\
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
# Reads sidecar progress file for richer context when available.
$null = $input | Out-Null
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
            Write-Host "Last validation: $total files, $gp" -ForegroundColor Cyan
            exit 0
        }
    } catch {}
}
# Check report sidecar
$reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $reportProgress) {
    try {
        $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
        if ($rd.status -eq "completed") {
            $results = @($rd.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "Last report: $($results.Count) files, avg $avg/100"
            }
        }
    } catch {}
}
Write-Host "Reminder: run tapps_validate_changed to confirm quality." -ForegroundColor Yellow
exit 0
""",
    "tapps-post-validate.ps1": """\
# TappsMCP PostToolUse hook (tapps_validate_changed)
# Reads the sidecar progress file and echoes a summary to the transcript.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $sec = [math]::Round($d.elapsed_ms / 1000.0, 1)
            $gp = if ($d.all_gates_passed) { "ALL PASSED" } else { "$failed FAILED" }
            Write-Output "[TappsMCP] Validation: $total files, $gp ($($sec)s)"
        } elseif ($d.status -eq "error") {
            Write-Output "[TappsMCP] Validation error: $($d.error)"
        } elseif ($d.status -eq "running") {
            Write-Output "[TappsMCP] Validation in progress: $($d.completed)/$($d.total) files"
        }
    } catch {}
}
exit 0
""",
    "tapps-post-report.ps1": """\
# TappsMCP PostToolUse hook (tapps_report)
# Reads the report sidecar progress file and echoes a summary.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $results = @($d.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "[TappsMCP] Report: $total files scored, avg $avg/100"
            } else {
                Write-Output "[TappsMCP] Report: $total files scored"
            }
        } elseif ($d.status -eq "error") {
            Write-Output "[TappsMCP] Report error: $($d.error)"
        } elseif ($d.status -eq "running") {
            Write-Output "[TappsMCP] Report in progress: $($d.completed)/$($d.total) files"
        }
    } catch {}
}
exit 0
""",
    "tapps-pre-compact.ps1": """\
# TappsMCP PreCompact hook
# Backs up scoring context before context window compaction.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
$backupDir = if ($projDir) { "$projDir/.tapps-mcp" } else { ".tapps-mcp" }
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}
$outFile = "$backupDir/pre-compact-context.json"
$rawInput | Set-Content -Path $outFile -Encoding UTF8
Write-Output "[TappsMCP] Scoring context backed up to $outFile"
exit 0
""",
    "tapps-subagent-start.ps1": """\
# TappsMCP SubagentStart hook
# Injects TappsMCP awareness into spawned subagents.
$null = $input | Out-Null
Write-Output "[TappsMCP] This project uses TappsMCP for code quality."
Write-Output "MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed, tapps_memory."
exit 0
""",
    "tapps-subagent-stop.ps1": """\
# TappsMCP SubagentStop hook (Epic 36.1)
# Advises on quality validation when subagent modified Python files.
# IMPORTANT: SubagentStop does NOT support exit code 2 (advisory only).
$rawInput = @($input) -join "`n"
$msg = "Subagent completed. Run tapps_quick_check or tapps_validate_changed"
Write-Host $msg -ForegroundColor Yellow
$msg2 = "on any Python files modified by this subagent."
Write-Host $msg2 -ForegroundColor Yellow
exit 0
""",
    "tapps-session-end.ps1": """\
# TappsMCP SessionEnd hook (Epic 36.2)
# Creates a quality summary at session end.
# IMPORTANT: SessionEnd does NOT support exit code 2 (advisory only).
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
if (Test-Path $marker) {
    Write-Host "[TappsMCP] Session quality validated." -ForegroundColor Green
} else {
    $msg = "[TappsMCP] Session ended without running quality validation."
    Write-Host $msg -ForegroundColor Yellow
    $msg2 = "Consider running tapps_validate_changed before ending sessions."
    Write-Host $msg2 -ForegroundColor Yellow
}
exit 0
""",
    "tapps-tool-failure.ps1": """\
# TappsMCP PostToolUseFailure hook (Epic 36.3 / TAP-976)
# Logs TappsMCP MCP tool failures for diagnostics.
# IMPORTANT: PostToolUseFailure does NOT support exit code 2 (advisory only).
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $tool = if ($data.tool_name) { [string]$data.tool_name } else { "" }
} catch {
    $tool = ""
    $data = $null
}
if ($tool -notmatch '^mcp__tapps[-_]mcp__') {
    exit 0
}
$err = if ($data -and $data.error) { [string]$data.error } else { "unknown error" }
$errorMsg = $err.Substring(0, [Math]::Min(200, $err.Length))
[Console]::Error.WriteLine("TappsMCP tool $tool failed: $errorMsg")
[Console]::Error.WriteLine("Run tapps_doctor to diagnose, or check MCP server connectivity.")
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
$dir = Join-Path $root '.tapps-mcp'
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$entry = @{ ts = $ts; tool = $tool; error = $errorMsg } | ConvertTo-Json -Compress
Add-Content -Path (Join-Path $dir '.failure-log.jsonl') -Value $entry
exit 0
""",
    "tapps-pre-bash.ps1": """\
# TappsMCP PreToolUse hook (Bash) - destructive command guard (opt-in)
# Blocks commands containing rm -rf, format c:, etc. Exit 2 = block, 0 = allow.
$raw = @($input) -join "`n"
$cmd = ""
try {
    $data = $raw | ConvertFrom-Json
    $ti = $data.tool_input
    if ($ti.command) { $cmd = $ti.command }
    elseif ($ti.args) { $cmd = ($ti.args | ForEach-Object { $_ }) -join " " }
} catch {}
$block = $false
if ($cmd -match 'rm\\s+-[rf]+' -and $cmd -match '/') { $block = $true }
if ($cmd -match 'format\\s+[cC]:') { $block = $true }
if ($cmd -match 'del\\s+/[fs]*\\s*/[sq]*' -or $cmd -match 'rd\\s+/s\\s+/q') { $block = $true }
if ($block) {
    Write-Error "TappsMCP: Blocked potentially destructive command."
    exit 2
}
exit 0
""",
    "tapps-memory-auto-capture.ps1": """\
# TappsMCP Stop hook - Auto-Capture (Epic 65.5)
# Extracts durable facts from context and saves via MemoryStore.
# Runs tapps-mcp auto-capture with stdin; configurable max_facts, min_context.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
try {
    if (Get-Command tapps-mcp -ErrorAction SilentlyContinue) {
        $rawInput | tapps-mcp auto-capture --project-root $projDir 2>$null
    } else {
        $rawInput | python -m tapps_mcp.cli auto-capture --project-root $projDir 2>$null
    }
} catch {}
exit 0
""",
    "tapps-memory-capture.ps1": """\
# TappsMCP Stop hook - Memory Capture (Epic 34.5)
# Writes session quality data to .tapps-mcp/session-capture.json for
# persistence into shared memory on next session start.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$captureDir = "$projDir/.tapps-mcp"
$marker = "$captureDir/.validation-marker"
$validated = if (Test-Path $marker) { $true } else { $false }
$dateStr = (Get-Date -Format "yyyy-MM-dd")
try {
    $gitOutput = git diff --name-only HEAD 2>$null
    $filesEdited = @($gitOutput | Where-Object { $_ -match '\\.py$' }).Count
} catch {
    $filesEdited = 0
}
if (-not (Test-Path $captureDir)) {
    New-Item -ItemType Directory -Path $captureDir -Force | Out-Null
}
$capture = @{ date = $dateStr; validated = $validated; files_edited = $filesEdited }
$capture | ConvertTo-Json | Set-Content -Path "$captureDir/session-capture.json" -Encoding UTF8
exit 0
""",
}

CLAUDE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-session-start.ps1"
                    ),
                },
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-session-compact.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write|MultiEdit",
            "if": "Edit(**/*.py) | Write(**/*.py) | MultiEdit(**/*.py)",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-edit.ps1"
                    ),
                },
            ],
        },
        {
            "matcher": "mcp__tapps-mcp__tapps_validate_changed",
            "if": "mcp__tapps-mcp__tapps_validate_changed",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-validate.ps1"
                    ),
                    "timeout": 10,
                },
            ],
        },
        {
            "matcher": "mcp__tapps-mcp__tapps_report",
            "if": "mcp__tapps-mcp__tapps_report",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-report.ps1"
                    ),
                    "timeout": 10,
                },
            ],
        },
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-stop.ps1"
                    ),
                },
            ],
        },
    ],
    "TaskCompleted": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-task-completed.ps1"
                    ),
                },
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-compact.ps1"
                    ),
                },
            ],
        },
    ],
    "SubagentStart": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-subagent-start.ps1"
                    ),
                },
            ],
        },
    ],
    "SubagentStop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-subagent-stop.ps1"
                    ),
                },
            ],
        },
    ],
    "SessionEnd": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-session-end.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUseFailure": [
        {
            "matcher": "mcp__tapps-mcp__.*",
            "if": "mcp__tapps-mcp__*",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-tool-failure.ps1"
                    ),
                },
            ],
        },
    ],
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-user-prompt-submit.ps1"
                    ),
                },
            ],
        },
    ],
}

CLAUDE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-session-start.sh"},
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-session-compact.sh"},
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write|MultiEdit",
            # TAP-955: `if:` narrows the hook to Python/infra edits only, so
            # tapps-post-edit.sh no longer spawns on every Edit of a markdown
            # or JSON file. Permission-rule syntax: ToolName(glob).
            "if": "Edit(**/*.py) | Write(**/*.py) | MultiEdit(**/*.py)",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-post-edit.sh"},
            ],
        },
        {
            "matcher": "mcp__tapps-mcp__tapps_validate_changed",
            "if": "mcp__tapps-mcp__tapps_validate_changed",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-validate.sh",
                    "timeout": 10,
                },
            ],
        },
        {
            "matcher": "mcp__tapps-mcp__tapps_report",
            "if": "mcp__tapps-mcp__tapps_report",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-post-report.sh", "timeout": 10},
            ],
        },
    ],
    "Stop": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-stop.sh"},
            ],
        },
    ],
    "TaskCompleted": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-task-completed.sh"},
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-pre-compact.sh"},
            ],
        },
    ],
    "SubagentStart": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-subagent-start.sh"},
            ],
        },
    ],
    "SubagentStop": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-subagent-stop.sh"},
            ],
        },
    ],
    "SessionEnd": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-session-end.sh"},
            ],
        },
    ],
    "PostToolUseFailure": [
        {
            "matcher": "mcp__tapps-mcp__.*",
            "if": "mcp__tapps-mcp__*",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-tool-failure.sh"},
            ],
        },
    ],
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-user-prompt-submit.sh",
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Cursor hook script templates (Story 12.7)
# ---------------------------------------------------------------------------

CURSOR_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-before-mcp.sh": """\
#!/usr/bin/env bash
# TappsMCP beforeMCPExecution hook
# Logs MCP tool invocations and reminds to call session_start.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('tool','unknown'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
TOOL=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
case "$TOOL" in
  tapps_*)
    SENTINEL="${TMPDIR:-/tmp}/.tapps-session-started-$$"
    if [ "$TOOL" = "tapps_session_start" ]; then
      touch "$SENTINEL"
    elif [ ! -f "$SENTINEL" ]; then
      echo "REMINDER: Call tapps_session_start() first for best results."
    fi
    ;;
esac
echo "[TappsMCP] MCP tool invoked: $TOOL" >&2
exit 0
""",
    "tapps-after-edit.sh": """\
#!/usr/bin/env bash
# TappsMCP afterFileEdit hook (fire-and-forget)
# Reminds the agent to check quality after file edits.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('file','unknown'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
FILE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
echo "File edited: $FILE"
echo "Consider running tapps_quick_check to verify quality."
exit 0
""",
}

# ---------------------------------------------------------------------------
# Cursor hook script templates - PowerShell (Windows)
# ---------------------------------------------------------------------------

CURSOR_HOOK_SCRIPTS_PS: dict[str, str] = {
    "tapps-before-mcp.ps1": """\
# TappsMCP beforeMCPExecution hook
# Logs MCP tool invocations and reminds to call session_start.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $tool = if ($data.tool) { $data.tool } else { "unknown" }
} catch {
    $tool = "unknown"
}
if ($tool -match '^tapps_') {
    $sentinel = "$env:TEMP\\.tapps-session-started-$PID"
    if ($tool -eq 'tapps_session_start') {
        $null = New-Item -ItemType File -Path $sentinel -Force
    } elseif (-not (Test-Path $sentinel)) {
        Write-Output "REMINDER: Call tapps_session_start() first for best results."
    }
}
Write-Host "[TappsMCP] MCP tool invoked: $tool" -ForegroundColor Cyan
exit 0
""",
    "tapps-after-edit.ps1": """\
# TappsMCP afterFileEdit hook (fire-and-forget)
# Reminds the agent to check quality after file edits.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $file = if ($data.file) { $data.file }
            elseif ($data.tool_input.file_path) { $data.tool_input.file_path }
            elseif ($data.tool_input.path) { $data.tool_input.path }
            else { "unknown" }
} catch {
    $file = "unknown"
}
Write-Output "File edited: $file"
Write-Output "Consider running tapps_quick_check to verify quality."
exit 0
""",
}

PS1_PREFIX = "powershell -NoProfile -ExecutionPolicy Bypass -File "

# Supported Cursor hooks.json event keys (schema: cursor-hooks/schema/hooks.schema.json).
# Only these keys are valid under "hooks"; invalid keys can cause the file to be ignored.
SUPPORTED_CURSOR_HOOK_KEYS: frozenset[str] = frozenset(
    {
        "beforeShellExecution",
        "beforeMCPExecution",
        "afterFileEdit",
        "beforeReadFile",
        "beforeSubmitPrompt",
        "stop",
    }
)

CURSOR_HOOKS_CONFIG: dict[str, list[dict[str, str]]] = {
    "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
    "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
}

CURSOR_HOOKS_CONFIG_PS: dict[str, list[dict[str, str]]] = {
    "beforeMCPExecution": [
        {"command": PS1_PREFIX + ".cursor/hooks/tapps-before-mcp.ps1"},
    ],
    "afterFileEdit": [
        {"command": PS1_PREFIX + ".cursor/hooks/tapps-after-edit.ps1"},
    ],
}

# ---------------------------------------------------------------------------
# Memory auto-capture hook config (Epic 65.5) — opt-in via memory_auto_capture=True
# ---------------------------------------------------------------------------

MEMORY_AUTO_CAPTURE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-capture.sh",
                },
            ],
        },
    ],
}

MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-auto-capture.ps1"
                    ),
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Memory capture hook config (Epic 34.5) — opt-in via memory_capture=True
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Memory auto-recall hook templates (Epic 65.4)
# Runs before agent prompt (PreCompact, SessionStart) to inject relevant memories.
# Calls tapps-mcp memory recall with query from prompt/last user message.
# Configurable: max_results (5), min_score (0.3), min_prompt_length (50).
# ---------------------------------------------------------------------------


def _memory_auto_recall_script(
    max_results: int = 5,
    min_score: float = 0.3,
    min_prompt_length: int = 50,
) -> str:
    """Return the bash script for memory auto-recall (Epic 65.4)."""
    return f"""#!/usr/bin/env bash
# TappsMCP Memory Auto-Recall (Epic 65.4)
# Injects relevant memories before agent prompt. Runs on PreCompact, SessionStart.
# Graceful fallback: no MemoryStore, MCP unavailable, empty results — exit 0.
INPUT=$(cat)
PY="import sys,json
try:
    d=json.load(sys.stdin)
    q=d.get('prompt','') or d.get('last_user_message','') or d.get('last_message','')
    if not q and 'messages' in d:
        ms=d.get('messages',[])
        if ms:
            last=ms[-1] if isinstance(ms[-1],dict) else {{}}
            q=last.get('content',last.get('text',''))
    if not q: q=d.get('context','') or 'project context architecture'
    q=(q or '')[:500]
    print(q)
except Exception:
    print('project context architecture')
"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
QUERY=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null || echo "project context architecture")
if [ ${{#QUERY}} -lt {min_prompt_length} ]; then
  exit 0
fi
PROJECT_DIR="${{CLAUDE_PROJECT_DIR:-.}}"
TAPPS=$(command -v tapps-mcp 2>/dev/null)
if [ -z "$TAPPS" ]; then
  exit 0
fi
OUT=$("$TAPPS" memory recall --query "$QUERY" --project-root "$PROJECT_DIR" \\
  --max-results {max_results} --min-score {min_score} 2>/dev/null)
if [ -n "$OUT" ]; then
  echo "$OUT"
fi
exit 0
"""


def _memory_auto_recall_script_ps(
    max_results: int = 5,
    min_score: float = 0.3,
    min_prompt_length: int = 50,
) -> str:
    """Return the PowerShell script for memory auto-recall (Epic 65.4)."""
    return f"""# TappsMCP Memory Auto-Recall (Epic 65.4)
# Injects relevant memories before agent prompt. Runs on PreCompact, SessionStart.
# Graceful fallback: no MemoryStore, MCP unavailable, empty results — exit 0.
$rawInput = @($input) -join "`n"
$query = "project context architecture"
try {{
    $data = $rawInput | ConvertFrom-Json
    $query = if ($data.prompt) {{ $data.prompt }}
             elseif ($data.last_user_message) {{ $data.last_user_message }}
             elseif ($data.last_message) {{ $data.last_message }}
             elseif ($data.context) {{ $data.context }}
             else {{ "project context architecture" }}
    if ($data.messages -and $data.messages.Count -gt 0) {{
        $last = $data.messages[-1]
        $c = if ($last.content) {{ $last.content }} elseif ($last.text) {{ $last.text }} else {{ "" }}
        if ($c) {{ $query = $c }}
    }}
    $query = ($query -as [string] -or "").Substring(0, [Math]::Min(500, ($query -as [string]).Length))
}} catch {{}}
if ($query.Length -lt {min_prompt_length}) {{
    exit 0
}}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) {{ $projDir = "." }}
$tapps = Get-Command tapps-mcp -ErrorAction SilentlyContinue
if (-not $tapps) {{
    exit 0
}}
try {{
    $out = & tapps-mcp memory recall --query "$query" --project-root $projDir `
        --max-results {max_results} --min-score {min_score} 2>$null
    if ($out) {{ Write-Output $out }}
}} catch {{}}
exit 0
"""


MEMORY_AUTO_RECALL_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-recall.sh",
                },
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-recall.sh",
                },
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-recall.sh",
                },
            ],
        },
    ],
}

MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-auto-recall.ps1"
                    ),
                },
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-auto-recall.ps1"
                    ),
                },
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-auto-recall.ps1"
                    ),
                },
            ],
        },
    ],
}

MEMORY_CAPTURE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-capture.sh",
                },
            ],
        },
    ],
}

MEMORY_CAPTURE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-capture.ps1"
                    ),
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Destructive command guard (opt-in PreToolUse hook)
# ---------------------------------------------------------------------------

DESTRUCTIVE_GUARD_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-pre-bash.sh"},
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Linear routing gate (TAP-981) — opt-in via linear_enforce_gate
# ---------------------------------------------------------------------------
#
# Two cooperating hooks:
#   1. PostToolUse on mcp__docs-mcp__docs_validate_linear_issue writes a
#      sentinel file with a timestamp whenever an agent validates a Linear
#      issue body against the template.
#   2. PreToolUse on mcp__plugin_linear_linear__save_issue reads that
#      sentinel and blocks the write if no validate call has happened in the
#      last 30 minutes — steering the agent back through the linear-issue
#      skill. Bypass with TAPPS_LINEAR_SKIP_VALIDATE=1 (logged).
#
# Kept independent of destructive_guard so projects can enable Linear routing
# enforcement without also enabling the bash destructive-command guard.

LINEAR_GATE_POST_VALIDATE_SCRIPT = """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook — Linear gate sentinel writer (TAP-981 / TAP-1328)
# Writes .tapps-mcp/.linear-validate-sentinel ONLY when the validate call
# returned agent_ready=true. Failed validations no longer unlock save_issue.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
PARSED=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json
try:
    d=json.load(sys.stdin)
    tool=d.get('tool_name') or d.get('toolName') or ''
    resp=d.get('tool_response') or d.get('toolResponse') or {}
    if isinstance(resp,str):
        try: resp=json.loads(resp)
        except Exception: resp={}
    data=resp.get('data') if isinstance(resp,dict) else None
    ready=False
    if isinstance(data,dict) and data.get('agent_ready') is True:
        ready=True
    elif isinstance(resp,dict) and resp.get('agent_ready') is True:
        ready=True
    print(tool)
    print('1' if ready else '0')
except Exception:
    print('')
    print('0')" 2>/dev/null)
TOOL=$(echo "$PARSED" | sed -n '1p')
READY=$(echo "$PARSED" | sed -n '2p')
case "$TOOL" in
  mcp__docs-mcp__docs_validate_linear_issue|docs_validate_linear_issue) ;;
  *) exit 0 ;;
esac
if [ "$READY" != "1" ]; then
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
date +%s > "$ROOT/.tapps-mcp/.linear-validate-sentinel" 2>/dev/null
exit 0
"""

LINEAR_GATE_PRE_SAVE_SCRIPT = """\
#!/usr/bin/env bash
# TappsMCP PreToolUse hook — Linear write gate (TAP-981)
# Blocks mcp__plugin_linear_linear__save_issue if no recent
# docs_validate_linear_issue sentinel (within 30 minutes). Bypass with
# TAPPS_LINEAR_SKIP_VALIDATE=1 (logged to .tapps-mcp/.bypass-log.jsonl).
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYBIN" ]; then
  # TAP-1785: enforcement gate fails closed when python is unavailable.
  ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
  mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
  echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"hook\\":\\"tapps-pre-linear-write\\",\\"reason\\":\\"no_python\\"}" \\
    >> "$ROOT/.tapps-mcp/.bypass-log.jsonl" 2>/dev/null
  echo "TappsMCP: Blocked Linear save_issue — no python interpreter available to evaluate the validation gate." >&2
  exit 2
fi
PARSED=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json
try:
    d=json.load(sys.stdin)
    name=d.get('tool_name') or d.get('toolName') or ''
    inp=d.get('tool_input') or d.get('toolInput') or {}
    has_id=bool(inp.get('id'))
    has_template=bool(inp.get('title')) or bool(inp.get('description'))
    update_only='1' if (has_id and not has_template) else '0'
    print(name)
    print(update_only)
except Exception:
    print('')
    print('0')" 2>/dev/null)
TOOL=$(echo "$PARSED" | sed -n '1p')
UPDATE_ONLY=$(echo "$PARSED" | sed -n '2p')
case "$TOOL" in
  mcp__plugin_linear_linear__save_issue|save_issue) ;;
  *) exit 0 ;;
esac
# Update-only allow-list (TAP-981 FP reduction): save_issue calls that target
# an existing issue (id present) and do NOT modify title/description skip the
# sentinel — status, priority, label, assignee, parent updates don't need a
# fresh template validation.
if [ "$UPDATE_ONLY" = "1" ]; then
  exit 0
fi
if [ "${TAPPS_LINEAR_SKIP_VALIDATE:-0}" = "1" ]; then
  ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
  mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
  echo "{\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"bypass\\":\\"TAPPS_LINEAR_SKIP_VALIDATE\\"}" \\
    >> "$ROOT/.tapps-mcp/.bypass-log.jsonl" 2>/dev/null
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
SENTINEL="$ROOT/.tapps-mcp/.linear-validate-sentinel"
if [ ! -f "$SENTINEL" ]; then
  cat >&2 <<'MSG'
TappsMCP: Blocked mcp__plugin_linear_linear__save_issue — no recent docs_validate_linear_issue call.
Route Linear writes through the `linear-issue` skill:
  1. docs_generate_story (or docs_generate_epic)
  2. docs_validate_linear_issue
  3. plugin save_issue
  4. tapps_linear_snapshot_invalidate
Or set TAPPS_LINEAR_SKIP_VALIDATE=1 for emergency bypass (logged).
See .claude/rules/linear-standards.md.
MSG
  exit 2
fi
NOW=$(date +%s)
SENT=$(cat "$SENTINEL" 2>/dev/null)
if ! echo "$SENT" | grep -Eq '^[0-9]+$'; then
  SENT=0
fi
AGE=$((NOW - SENT))
# Allow if validated within last 1800 seconds (30 minutes).
if [ "$AGE" -le 1800 ]; then
  exit 0
fi
cat >&2 <<MSG
TappsMCP: Blocked mcp__plugin_linear_linear__save_issue — last docs_validate_linear_issue was ${AGE}s ago (> 1800s freshness window).
Re-validate before push: docs_validate_linear_issue(title=..., description=..., ...)
Or set TAPPS_LINEAR_SKIP_VALIDATE=1 for emergency bypass (logged).
See .claude/rules/linear-standards.md.
MSG
exit 2
"""

LINEAR_GATE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "mcp__plugin_linear_linear__save_issue",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-pre-linear-write.sh",
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "mcp__docs-mcp__docs_validate_linear_issue",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-docs-validate.sh",
                },
            ],
        },
    ],
}

LINEAR_GATE_SCRIPTS: dict[str, str] = {
    "tapps-pre-linear-write.sh": LINEAR_GATE_PRE_SAVE_SCRIPT,
    "tapps-post-docs-validate.sh": LINEAR_GATE_POST_VALIDATE_SCRIPT,
}

# ---------------------------------------------------------------------------
# Linear routing gate — PowerShell variants (TAP-986)
# ---------------------------------------------------------------------------
# Windows equivalents of the bash gate. Sentinel path + behavior must match
# the bash originals so an agent switching platforms sees the same gate.
# `[DateTimeOffset]::Now.ToUnixTimeSeconds()` is the PS match for bash
# `date +%s`; `Test-Path` is the match for `[ -f ... ]`.

LINEAR_GATE_POST_VALIDATE_SCRIPT_PS = """\
# TappsMCP PostToolUse hook — Linear gate sentinel writer (TAP-981/TAP-986)
# Writes .tapps-mcp/.linear-validate-sentinel with current Unix epoch seconds
# whenever an agent calls mcp__docs-mcp__docs_validate_linear_issue. Paired
# with tapps-pre-linear-write.ps1 which reads the sentinel to decide whether
# to allow a downstream save_issue.
$stdin = [Console]::In.ReadToEnd()
$tool = ""
try {
    $d = $stdin | ConvertFrom-Json
    if ($d.tool_name) { $tool = [string]$d.tool_name }
    elseif ($d.toolName) { $tool = [string]$d.toolName }
} catch {}
if ($tool -eq 'mcp__docs-mcp__docs_validate_linear_issue' -or $tool -eq 'docs_validate_linear_issue') {
    $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
    $dir = Join-Path $root '.tapps-mcp'
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $ts = [int64]([DateTimeOffset]::Now.ToUnixTimeSeconds())
    Set-Content -Path (Join-Path $dir '.linear-validate-sentinel') -Value $ts -Encoding UTF8
}
exit 0
"""

LINEAR_GATE_PRE_SAVE_SCRIPT_PS = """\
# TappsMCP PreToolUse hook — Linear write gate (TAP-981/TAP-986)
# Blocks mcp__plugin_linear_linear__save_issue if no recent
# docs_validate_linear_issue sentinel (within 30 minutes). Bypass with
# TAPPS_LINEAR_SKIP_VALIDATE=1 (logged to .tapps-mcp/.bypass-log.jsonl).
$stdin = [Console]::In.ReadToEnd()
$tool = ""
$updateOnly = $false
try {
    $d = $stdin | ConvertFrom-Json
    if ($d.tool_name) { $tool = [string]$d.tool_name }
    elseif ($d.toolName) { $tool = [string]$d.toolName }
    $inp = $null
    if ($d.PSObject.Properties.Name -contains 'tool_input') { $inp = $d.tool_input }
    elseif ($d.PSObject.Properties.Name -contains 'toolInput') { $inp = $d.toolInput }
    if ($inp) {
        $hasId = [bool]($inp.PSObject.Properties.Name -contains 'id' -and $inp.id)
        $hasTemplate = [bool](
            ($inp.PSObject.Properties.Name -contains 'title' -and $inp.title) -or
            ($inp.PSObject.Properties.Name -contains 'description' -and $inp.description)
        )
        if ($hasId -and -not $hasTemplate) { $updateOnly = $true }
    }
} catch {}
if ($tool -ne 'mcp__plugin_linear_linear__save_issue' -and $tool -ne 'save_issue') {
    exit 0
}
# Update-only allow-list (TAP-981 FP reduction): metadata-only updates skip the sentinel.
if ($updateOnly) {
    exit 0
}
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
$dir = Join-Path $root '.tapps-mcp'
if ($env:TAPPS_LINEAR_SKIP_VALIDATE -eq '1') {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $nowIso = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $entry = @{ ts = $nowIso; bypass = 'TAPPS_LINEAR_SKIP_VALIDATE' } | ConvertTo-Json -Compress
    Add-Content -Path (Join-Path $dir '.bypass-log.jsonl') -Value $entry
    exit 0
}
$sentinel = Join-Path $dir '.linear-validate-sentinel'
if (-not (Test-Path $sentinel)) {
    [Console]::Error.WriteLine("TappsMCP: Blocked mcp__plugin_linear_linear__save_issue - no recent docs_validate_linear_issue call.")
    [Console]::Error.WriteLine("Route Linear writes through the linear-issue skill:")
    [Console]::Error.WriteLine("  1. docs_generate_story (or docs_generate_epic)")
    [Console]::Error.WriteLine("  2. docs_validate_linear_issue")
    [Console]::Error.WriteLine("  3. plugin save_issue")
    [Console]::Error.WriteLine("  4. tapps_linear_snapshot_invalidate")
    [Console]::Error.WriteLine("Or set TAPPS_LINEAR_SKIP_VALIDATE=1 for emergency bypass (logged).")
    [Console]::Error.WriteLine("See .claude/rules/linear-standards.md.")
    exit 2
}
$now = [int64]([DateTimeOffset]::Now.ToUnixTimeSeconds())
$raw = ""
try {
    $raw = (Get-Content -Path $sentinel -Raw -ErrorAction Stop).Trim()
} catch {}
if ($raw -notmatch '^[0-9]+$') {
    $sent = [int64]0
} else {
    $sent = [int64]$raw
}
$age = $now - $sent
if ($age -le 1800) {
    exit 0
}
[Console]::Error.WriteLine("TappsMCP: Blocked mcp__plugin_linear_linear__save_issue - last docs_validate_linear_issue was ${age}s ago (> 1800s freshness window).")
[Console]::Error.WriteLine("Re-validate before push: docs_validate_linear_issue(title=..., description=..., ...)")
[Console]::Error.WriteLine("Or set TAPPS_LINEAR_SKIP_VALIDATE=1 for emergency bypass (logged).")
[Console]::Error.WriteLine("See .claude/rules/linear-standards.md.")
exit 2
"""

LINEAR_GATE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "mcp__plugin_linear_linear__save_issue",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-linear-write.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "mcp__docs-mcp__docs_validate_linear_issue",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-docs-validate.ps1"
                    ),
                },
            ],
        },
    ],
}

LINEAR_GATE_SCRIPTS_PS: dict[str, str] = {
    "tapps-pre-linear-write.ps1": LINEAR_GATE_PRE_SAVE_SCRIPT_PS,
    "tapps-post-docs-validate.ps1": LINEAR_GATE_POST_VALIDATE_SCRIPT_PS,
}

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
# then list_issues with a concrete state. Without alias support the keys
# differ and the gate self-trips (TAP-1374). Fix: derive a bucket alias and
# emit additional sentinels for it. Same logic on both sides.
OPEN_BUCKET = ('backlog', 'unstarted', 'started', 'triage')
state_lc = state.lower()
def _key_for(state_part: str) -> str:
    filt = {k: v for k, v in sorted({
        'state': state_part, 'label': label, 'limit': limit,
    }.items()) if v not in (None, '')}
    payload = json.dumps(filt, sort_keys=True, default=str).encode('utf-8')
    fhash = hashlib.sha256(payload).hexdigest()[:16]
    parts = [
        (team.replace('/', '_') or '_'),
        (project.replace('/', '_') or '_'),
        ((state_part or 'any').replace('/', '_')),
        fhash,
    ]
    return '__'.join(parts)
key = _key_for(state)
# Bucket alias keys: when state is 'open' (a tapps-mcp alias), '' (any), or
# any open-bucket member, every other open-bucket member should resolve.
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
  mcp__tapps-mcp__tapps_linear_snapshot_get|tapps_linear_snapshot_get) ;;
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
  mcp__plugin_linear_linear__list_issues|list_issues) ;;
  *) exit 0 ;;
esac
if [ -z "$KEY" ]; then
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
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
LINEAR_CACHE_GATE_POST_LIST_SCRIPT = (
    """\
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
echo "$INPUT" | TAPPS_PROJECT_ROOT="$ROOT" "$PYBIN" -c "
import sys, os, json, hashlib, time
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
name = d.get('tool_name') or d.get('toolName') or ''
if name not in ('mcp__plugin_linear_linear__list_issues', 'list_issues'):
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
if not team or not project:
    sys.exit(0)
filt = {k: v for k, v in sorted({
    'state': state, 'label': label, 'limit': limit,
}.items()) if v not in (None, '')}
payload = json.dumps(filt, sort_keys=True, default=str).encode('utf-8')
fhash = hashlib.sha256(payload).hexdigest()[:16]
key = '__'.join([
    team.replace('/', '_') or '_',
    project.replace('/', '_') or '_',
    (state or 'any').replace('/', '_'),
    fhash,
])
resp = d.get('tool_response') or d.get('toolResponse') or {}
if isinstance(resp, str):
    try:
        resp = json.loads(resp)
    except Exception:
        resp = {}
def _find_issues(o):
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
issues = _find_issues(resp) or []
# TTL aligned with server-side _ttl_for_state defaults (5 min open, 1 h closed).
state_lc = state.lower()
ttl = 3600 if state_lc in ('completed', 'canceled') else 300
now = time.time()
out = {
    'issues': issues,
    'cached_at': now,
    'expires_at': now + ttl,
    'state': state or None,
    'team': team,
    'project': project,
    'auto_populated': True,
}
root = os.environ.get('TAPPS_PROJECT_ROOT') or os.getcwd()
cache_dir = os.path.join(root, '.tapps-mcp-cache', 'linear-snapshots')
try:
    os.makedirs(cache_dir, exist_ok=True)
    target = os.path.join(cache_dir, key + '.json')
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
" 2>/dev/null
exit 0
"""
)

LINEAR_CACHE_GATE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "mcp__plugin_linear_linear__list_issues",
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
            "matcher": "mcp__tapps-mcp__tapps_linear_snapshot_get",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-linear-snapshot-get.sh",
                },
            ],
        },
        {
            "matcher": "mcp__plugin_linear_linear__list_issues",
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
    $filtObj = [ordered]@{}
    if ($state) { $filtObj['state'] = $state }
    if ($label) { $filtObj['label'] = $label }
    if ($limit) { $filtObj['limit'] = $limit }
    $payload = ($filtObj | ConvertTo-Json -Compress)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLower().Substring(0, 16)
    $teamPart = if ($team) { $team.Replace('/', '_') } else { '_' }
    $projPart = if ($project) { $project.Replace('/', '_') } else { '_' }
    $statePart = if ($state) { $state.Replace('/', '_') } else { 'any' }
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
if ($tool -ne 'mcp__tapps-mcp__tapps_linear_snapshot_get' -and $tool -ne 'tapps_linear_snapshot_get') {
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
if ($tool -ne 'mcp__plugin_linear_linear__list_issues' -and $tool -ne 'list_issues') {
    exit 0
}
"""
    + LINEAR_CACHE_GATE_KEY_PS
    + """\
if (-not $key) { exit 0 }
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $PWD.Path }
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
    [Console]::Error.WriteLine("TappsMCP: Linear cache-first read rule (TAP-1224, warn mode) - no recent tapps_linear_snapshot_get for this slice.")
    [Console]::Error.WriteLine("Route reads through the linear-read skill. Allowed (warn) but logged to .tapps-mcp/.cache-gate-violations.jsonl.")
    [Console]::Error.WriteLine("See .claude/rules/linear-standards.md.")
    exit 0
}
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
            "matcher": "mcp__plugin_linear_linear__list_issues",
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
            "matcher": "mcp__tapps-mcp__tapps_linear_snapshot_get",
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
    chosen = mode if mode in ("warn", "block") else "warn"
    src = LINEAR_CACHE_GATE_SCRIPTS_PS if win else LINEAR_CACHE_GATE_SCRIPTS
    return {name: body.replace("__CACHE_GATE_MODE__", chosen) for name, body in src.items()}


DESTRUCTIVE_GUARD_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-bash.ps1"
                    ),
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Reactive event templates (TAP-956) — opt-in via .tapps-mcp.yaml
# ---------------------------------------------------------------------------
#
# Each entry in REACTIVE_HOOK_FLAGS maps an opt-in config key to the scripts
# + event wiring it enables. All five are off by default for backward compat.

REACTIVE_HOOK_FLAGS: tuple[str, ...] = (
    "cwd_reload",  # CwdChanged → re-reads .tapps-mcp.yaml
    "permission_retry",  # PermissionDenied → returns {retry: true} for safe tapps-* denials
    "session_title",  # UserPromptSubmit → emits hookSpecificOutput.sessionTitle
    "worktree_track",  # WorktreeCreate + WorktreeRemove
)

CLAUDE_REACTIVE_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-cwd-changed.sh": """\
#!/usr/bin/env bash
# TappsMCP CwdChanged hook — marks the config cache stale so the next
# tapps-mcp tool call re-reads .tapps-mcp.yaml from the new cwd.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
mkdir -p "$PROJECT_DIR/.tapps-mcp"
touch "$PROJECT_DIR/.tapps-mcp/.cwd-reload-marker"
echo "{}"
""",
    "tapps-permission-denied.sh": """\
#!/usr/bin/env bash
# TappsMCP PermissionDenied hook — retries safe auto-mode denials for
# mcp__tapps-mcp__* read-only tools. Returns {retry: true} when recoverable.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
echo "$INPUT" | "$PYBIN" -c "
import json, sys
d = json.load(sys.stdin)
tool = (d.get('tool_name') or '').lower()
if tool.startswith('mcp__tapps-mcp__'):
    print(json.dumps({'retry': True}))
else:
    print('{}')
"
""",
    "tapps-session-title.sh": """\
#!/usr/bin/env bash
# TappsMCP UserPromptSubmit hook — auto-names sessions from the first prompt.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
echo "$INPUT" | "$PYBIN" -c "
import json, sys
d = json.load(sys.stdin)
prompt = (d.get('prompt') or '').strip()
first = next((line.strip() for line in prompt.splitlines() if line.strip()), 'TappsMCP session')
print(json.dumps({'hookSpecificOutput': {'sessionTitle': first[:60]}}))
"
""",
    "tapps-worktree-create.sh": """\
#!/usr/bin/env bash
# TappsMCP WorktreeCreate hook — logs worktree creation for review-fixer
# orchestration. Activity log lives in .tapps-mcp/worktree-activity.log.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="$PROJECT_DIR/.tapps-mcp"
mkdir -p "$LOG_DIR"
echo "$(date -Iseconds) WorktreeCreate: $INPUT" >> "$LOG_DIR/worktree-activity.log"
echo "{}"
""",
    "tapps-worktree-remove.sh": """\
#!/usr/bin/env bash
# TappsMCP WorktreeRemove hook — records cleanup so the review-fixer agent
# doesn't rely on the 2-hour zombie-process sweep to tidy up artifacts.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="$PROJECT_DIR/.tapps-mcp"
mkdir -p "$LOG_DIR"
echo "$(date -Iseconds) WorktreeRemove: $INPUT" >> "$LOG_DIR/worktree-activity.log"
echo "{}"
""",
}

CLAUDE_REACTIVE_HOOK_SCRIPTS_PS: dict[str, str] = {
    "tapps-cwd-changed.ps1": """\
# TappsMCP CwdChanged hook
$input | Out-Null
$dir = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { '.' }
New-Item -ItemType Directory -Force -Path "$dir/.tapps-mcp" | Out-Null
New-Item -ItemType File -Force -Path "$dir/.tapps-mcp/.cwd-reload-marker" | Out-Null
Write-Output '{}'
""",
    "tapps-permission-denied.ps1": """\
# TappsMCP PermissionDenied hook — retries safe tapps-* denials.
$stdin = [Console]::In.ReadToEnd()
$d = $stdin | ConvertFrom-Json
$tool = ($d.tool_name | Out-String).Trim().ToLower()
if ($tool.StartsWith('mcp__tapps-mcp__')) {
    Write-Output (@{retry=$true} | ConvertTo-Json -Compress)
} else {
    Write-Output '{}'
}
""",
    "tapps-session-title.ps1": """\
# TappsMCP UserPromptSubmit hook — auto-names session from first prompt.
$stdin = [Console]::In.ReadToEnd()
$d = $stdin | ConvertFrom-Json
$prompt = ($d.prompt | Out-String)
$first = ($prompt -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
if (-not $first) { $first = 'TappsMCP session' }
$title = $first.Substring(0, [Math]::Min(60, $first.Length))
Write-Output (@{hookSpecificOutput=@{sessionTitle=$title}} | ConvertTo-Json -Compress)
""",
    "tapps-worktree-create.ps1": """\
# TappsMCP WorktreeCreate hook
$stdin = [Console]::In.ReadToEnd()
$dir = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { '.' }
$logDir = "$dir/.tapps-mcp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = (Get-Date).ToString('o')
Add-Content -Path "$logDir/worktree-activity.log" -Value "$ts WorktreeCreate: $stdin"
Write-Output '{}'
""",
    "tapps-worktree-remove.ps1": """\
# TappsMCP WorktreeRemove hook
$stdin = [Console]::In.ReadToEnd()
$dir = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { '.' }
$logDir = "$dir/.tapps-mcp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = (Get-Date).ToString('o')
Add-Content -Path "$logDir/worktree-activity.log" -Value "$ts WorktreeRemove: $stdin"
Write-Output '{}'
""",
}


def _reactive_config(flag: str, *, win: bool) -> dict[str, list[dict[str, Any]]]:
    """Return the hooks.json fragment enabled by *flag*.

    Keeps opt-in state colocated with the scripts so callers don't have to
    duplicate the event-to-script wiring.
    """
    ext = "ps1" if win else "sh"
    cmd_prefix = "powershell -NoProfile -ExecutionPolicy Bypass -File " if win else ""
    if flag == "cwd_reload":
        return {
            "CwdChanged": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{cmd_prefix}.claude/hooks/tapps-cwd-changed.{ext}",
                        },
                    ],
                },
            ],
        }
    if flag == "permission_retry":
        return {
            "PermissionDenied": [
                {
                    "matcher": "mcp__tapps-mcp__.*",
                    "if": "mcp__tapps-mcp__*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (f"{cmd_prefix}.claude/hooks/tapps-permission-denied.{ext}"),
                        },
                    ],
                },
            ],
        }
    if flag == "session_title":
        return {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{cmd_prefix}.claude/hooks/tapps-session-title.{ext}",
                        },
                    ],
                },
            ],
        }
    if flag == "worktree_track":
        return {
            "WorktreeCreate": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{cmd_prefix}.claude/hooks/tapps-worktree-create.{ext}",
                        },
                    ],
                },
            ],
            "WorktreeRemove": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{cmd_prefix}.claude/hooks/tapps-worktree-remove.{ext}",
                        },
                    ],
                },
            ],
        }
    raise ValueError(f"Unknown reactive hook flag: {flag!r}")


def reactive_hook_scripts(enabled: dict[str, bool], *, win: bool) -> dict[str, str]:
    """Select reactive hook scripts to ship based on enabled opt-in flags."""
    scripts = CLAUDE_REACTIVE_HOOK_SCRIPTS_PS if win else CLAUDE_REACTIVE_HOOK_SCRIPTS
    out: dict[str, str] = {}
    ext = "ps1" if win else "sh"
    for flag, on in enabled.items():
        if not on:
            continue
        if flag == "cwd_reload":
            out[f"tapps-cwd-changed.{ext}"] = scripts[f"tapps-cwd-changed.{ext}"]
        elif flag == "permission_retry":
            out[f"tapps-permission-denied.{ext}"] = scripts[f"tapps-permission-denied.{ext}"]
        elif flag == "session_title":
            out[f"tapps-session-title.{ext}"] = scripts[f"tapps-session-title.{ext}"]
        elif flag == "worktree_track":
            out[f"tapps-worktree-create.{ext}"] = scripts[f"tapps-worktree-create.{ext}"]
            out[f"tapps-worktree-remove.{ext}"] = scripts[f"tapps-worktree-remove.{ext}"]
    return out


def reactive_hooks_config(
    enabled: dict[str, bool], *, win: bool
) -> dict[str, list[dict[str, Any]]]:
    """Merged hooks.json fragment for all enabled reactive-event flags."""
    merged: dict[str, list[dict[str, Any]]] = {}
    for flag, on in enabled.items():
        if not on:
            continue
        for event, entries in _reactive_config(flag, win=win).items():
            merged.setdefault(event, []).extend(entries)
    return merged


# ---------------------------------------------------------------------------
# Engagement-level blocking hook variants (Epic 36.5)
# ---------------------------------------------------------------------------

CLAUDE_HOOK_SCRIPTS_BLOCKING: dict[str, str] = {
    "tapps-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook (HIGH engagement - BLOCKING)
# Blocks task completion if validation has not been run.
# Reads sidecar for richer context in systemMessage.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -f "$MARKER" ]; then
  AGE=$("$PYBIN" -c "
import time
try:
    t=float(open('$MARKER').read().strip())
    print(int(time.time()-t))
except Exception:
    print(9999)
" 2>/dev/null)
  if [ "${AGE:-9999}" -gt 3600 ]; then
    echo "BLOCKED: Validation marker is stale (>1h). Run tapps_validate_changed." >&2
    exit 2
  fi
  # Marker is fresh — emit sidecar summary if available
  if [ -f "$PROGRESS" ]; then
    "$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
        for r in d.get('results',[]):
            if not r.get('gate_passed'):
                print(f'  FAILED: {r[\"file\"]} ({r.get(\"score\",\"?\")}/100)')
except Exception:
    pass
" 2>/dev/null
  fi
  # Check report sidecar
  REPORT_PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
  if [ -f "$REPORT_PROGRESS" ]; then
    REPORT_SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$REPORT_PROGRESS'))
    if d.get('status')=='completed':
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'Last report: {len(results)} files, avg {avg:.1f}/100')
except Exception:
    pass
" 2>/dev/null)
    [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
  fi
  exit 0
fi
echo "BLOCKED: tapps_validate_changed has not been run." >&2
echo "Run it before completing this task." >&2
exit 2
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook (HIGH engagement - BLOCKING on first invocation)
# Blocks if no quality validation was run this session.
# Reads sidecar for richer context when validation was run.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
if [ -f "$MARKER" ]; then
  # Emit sidecar summary if available
  if [ -f "$PROGRESS" ]; then
    "$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
except Exception:
    pass
" 2>/dev/null
  fi
  # Check report sidecar
  REPORT_PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
  if [ -f "$REPORT_PROGRESS" ]; then
    REPORT_SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$REPORT_PROGRESS'))
    if d.get('status')=='completed':
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'Last report: {len(results)} files, avg {avg:.1f}/100')
except Exception:
    pass
" 2>/dev/null)
    [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
  fi
  exit 0
fi
echo "BLOCKED: No quality validation was run this session." >&2
echo "Before declaring complete, run /tapps-finish-task (or tapps_validate_changed + tapps_checklist manually)." >&2
exit 2
""",
}

CLAUDE_HOOK_SCRIPTS_BLOCKING_PS: dict[str, str] = {
    "tapps-task-completed.ps1": """\
# TappsMCP TaskCompleted hook (HIGH engagement - BLOCKING)
# Blocks task completion if validation has not been run.
# Reads sidecar for richer context in systemMessage.
$null = $input | Out-Null
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $marker) {
    $content = Get-Content $marker -Raw
    try {
        $ts = [double]$content.Trim()
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $age = $now - $ts
        if ($age -gt 3600) {
            $m = "BLOCKED: Validation stale (>1h). Run tapps_validate_changed."
            Write-Host $m -ForegroundColor Red
            exit 2
        }
    } catch {
        $m = "BLOCKED: Invalid marker. Run tapps_validate_changed."
        Write-Host $m -ForegroundColor Red
        exit 2
    }
    if (Test-Path $progress) {
        try {
            $d = Get-Content $progress -Raw | ConvertFrom-Json
            if ($d.status -eq "completed") {
                $total = $d.total
                $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
                $failed = $total - $passed
                $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
                Write-Output "Last validation: $total files, $gp"
                foreach ($r in $d.results) {
                    if (-not $r.gate_passed) {
                        Write-Output "  FAILED: $($r.file) ($($r.score)/100)"
                    }
                }
            }
        } catch {}
    }
    # Check report sidecar
    $reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
    if (Test-Path $reportProgress) {
        try {
            $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
            if ($rd.status -eq "completed") {
                $results = @($rd.results)
                if ($results.Count -gt 0) {
                    $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                    Write-Output "Last report: $($results.Count) files, avg $avg/100"
                }
            }
        } catch {}
    }
    exit 0
}
Write-Host "BLOCKED: tapps_validate_changed has not been run." -ForegroundColor Red
Write-Host "Run it before completing this task." -ForegroundColor Red
exit 2
""",
    "tapps-stop.ps1": """\
# TappsMCP Stop hook (HIGH engagement - BLOCKING on first invocation)
# Blocks if no quality validation was run this session.
# Reads sidecar for richer context when validation was run.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $marker) {
    if (Test-Path $progress) {
        try {
            $d = Get-Content $progress -Raw | ConvertFrom-Json
            if ($d.status -eq "completed") {
                $total = $d.total
                $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
                $failed = $total - $passed
                $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
                Write-Output "Last validation: $total files, $gp"
            }
        } catch {}
    }
    # Check report sidecar
    $reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
    if (Test-Path $reportProgress) {
        try {
            $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
            if ($rd.status -eq "completed") {
                $results = @($rd.results)
                if ($results.Count -gt 0) {
                    $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                    Write-Output "Last report: $($results.Count) files, avg $avg/100"
                }
            }
        } catch {}
    }
    exit 0
}
Write-Host "BLOCKED: No quality validation was run this session." -ForegroundColor Red
Write-Host "Before declaring complete, run /tapps-finish-task (or tapps_validate_changed + tapps_checklist manually)." -ForegroundColor Red
exit 2
""",
}

# ---------------------------------------------------------------------------
# Prompt-type hook configuration (Epic 36.4) — opt-in
# ---------------------------------------------------------------------------

PROMPT_HOOK_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "type": "prompt",
            "prompt": (
                "A file was just modified. Based on this tool output: "
                "$ARGUMENTS\n\nWas a Python file (.py) changed in a way "
                "that could affect code quality? If Python code was added, "
                "modified, or deleted, answer 'yes'. If only comments, "
                "whitespace, or non-Python files were changed, answer 'no'."
            ),
            "model": "haiku",
            "timeout": 15,
        },
    ],
}

# ---------------------------------------------------------------------------
# Supported Claude Code lifecycle hooks (schema: claude-code-settings.json)
# ---------------------------------------------------------------------------
# Keys known to break Claude Code's settings.json schema.  Previously this
# was an allowlist, but that silently dropped user-added hook entries for any
# key TappsMCP hadn't yet catalogued (e.g. ralph's StopFailure).  Filtering
# by exclusion preserves user intent while still stripping the one known-bad
# key that causes Claude Code to reject the entire file.
INVALID_CLAUDE_HOOK_KEYS: frozenset[str] = frozenset({"PostCompact"})

# Retained for backward compatibility; callers should prefer the
# ``INVALID_CLAUDE_HOOK_KEYS``-based exclusion pattern used below.
SUPPORTED_CLAUDE_HOOK_KEYS: frozenset[str] = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "PermissionDenied",
        "Notification",
        "UserPromptSubmit",
        "Stop",
        "StopFailure",
        "SubagentStart",
        "SubagentStop",
        "PreCompact",
        "TeammateIdle",
        "TaskCompleted",
        "Setup",
        "InstructionsLoaded",
        "ConfigChange",
        "CwdChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "SessionStart",
        "SessionEnd",
    }
)

# ---------------------------------------------------------------------------
# Engagement-level hook event sets (Epic 36.6)
# ---------------------------------------------------------------------------

# Events to include per engagement level (for generate_claude_hooks filtering)
ENGAGEMENT_HOOK_EVENTS: dict[str, set[str]] = {
    "high": {
        "SessionStart",
        "PostToolUse",
        "Stop",
        "TaskCompleted",
        "PreCompact",
        "SubagentStart",
        "SubagentStop",
        "SessionEnd",
        "PostToolUseFailure",
        # TAP-975: per-prompt pipeline-state reminder (script self-silences
        # when session_start was within 30 min and no checklist is open).
        "UserPromptSubmit",
    },
    "medium": {
        "SessionStart",
        "PostToolUse",
        "Stop",
        "TaskCompleted",
        "PreCompact",
        "SubagentStart",
        "SubagentStop",
        # TAP-975: same hook at medium — same self-silencing logic, so the
        # noise floor is the same as high. The AC differentiates "fire
        # always" vs "fire on stale" but the script handles both via the
        # internal silence check, so the wiring is identical.
        "UserPromptSubmit",
    },
    "low": {
        "SessionStart",
    },
}

# ---------------------------------------------------------------------------
# Agent Teams hook templates (Story 12.12)
# ---------------------------------------------------------------------------

AGENT_TEAMS_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-teammate-idle.sh": """\
#!/usr/bin/env bash
# TappsMCP TeammateIdle hook
# Keeps quality watchdog active while gates are pending.
set -euo pipefail

INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin)"
PY="$PY; print(d.get('teammate_name',''))"
TEAMMATE=$(echo "$INPUT" | python3 -c "$PY" 2>/dev/null)

# Only keep the quality watchdog active
if [[ "$TEAMMATE" != "tapps-quality-watchdog" ]]; then
  exit 0
fi

echo "Quality watchdog — monitoring for issues" >&2
exit 2
""",
    "tapps-teams-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook (Agent Teams)
# Blocks task completion if quality gates fail.
set -euo pipefail

INPUT=$(cat)
MSG="Task blocked: run tapps_validate_changed"
MSG="$MSG to verify quality gates pass."
echo "$MSG" >&2
exit 2
""",
}

AGENT_TEAMS_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "TeammateIdle": [
        {
            "matcher": "tapps-quality-watchdog",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-teammate-idle.sh",
                },
            ],
        },
    ],
    "TaskCompleted": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (".claude/hooks/tapps-teams-task-completed.sh"),
                },
            ],
        },
    ],
}

AGENT_TEAMS_CLAUDE_MD_SECTION = """\

## Agent Teams (Optional)

If using Claude Code Agent Teams
(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`),
designate one teammate as a **quality watchdog**:

1. The quality watchdog runs `tapps_quick_check` on files changed
   by other teammates.
2. It messages other teammates via the shared mailbox when quality
   issues are found.
3. The `TaskCompleted` hook prevents any task from being marked
   complete until `tapps_validate_changed` passes.
4. The `TeammateIdle` hook keeps the watchdog active while quality
   issues remain unresolved.

To enable Agent Teams hooks, re-run `tapps_init` with
`agent_teams=True`.
"""
