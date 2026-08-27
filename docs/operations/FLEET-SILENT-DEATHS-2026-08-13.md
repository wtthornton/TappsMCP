# Forensics — fleet silent deaths, 2026-08-13 (TAP-6053)

**Status:** root cause of the *silence* named and fixed; the *sender* of the killing
signal is bounded, not identified (the evidence that would identify it is gone).

Companion doc: [FLEET-MAINTENANCE.md](FLEET-MAINTENANCE.md). Architecture:
[ADR-0024](../adr/0024-shared-http-mcp-fleet.md).

---

## 1. What happened

Twice on 2026-08-13 the six-server HTTP fleet went down with nothing surfaced to the
operator. The watchdog restarted it both times, a poll interval late:

| Event | Death (observed) | Restart marker in every server log |
|---|---|---|
| 1 | ~10:22 PDT, all six | `--- fleet start 2026-08-13T10:24:23 ---` |
| 2 | ~10:52 PDT | `--- fleet start 2026-08-13T10:53:14 ---` |

Death→restart for event 1 was **143 s**, which matches the debounce arithmetic in §5.

## 2. Evidence that survived, and what did not

**Gone — systemd journals.** The user journal no longer reaches 2026-08-13:

```
$ journalctl --user --since "2026-08-13 10:00" --until "2026-08-13 11:30"
-- No entries --

$ journalctl --user --list-boots
 -1  697fd249…  Thu 2026-08-20 13:36:11 PDT  Wed 2026-08-26 08:20:54 PDT
  0  7b17fc8f…  Wed 2026-08-26 08:24:33 PDT  Wed 2026-08-26 19:14:09 PDT
```

Earliest retained user-journal entry: **2026-08-20 13:36:11 PDT**. So there is no
`systemctl status`, no exit-code record, and no `_PID` correlation for the incident
window. `/etc/systemd/journald.conf` carries no overrides (bare `[Journal]`); current
user journals occupy 421.4 MB, so the 08-13 data was rotated out under the default
size cap, not deleted deliberately.

**Survived — the fleet's own append-only logs.** `start_fleet` opens
`~/.tapps-mcp/fleet/logs/<server_id>.log` in `"a"` mode
(`packages/tapps-mcp/src/tapps_mcp/distribution/fleet_control.py:324-333`) and nothing
ever rotates or truncates them. `nlt-build.log` is 72 MB and still contains 2026-08-13.
This is the only reason the incident is diagnosable at all.

## 3. The decisive lines

All six logs, immediately before both restart markers, end with the *same* frame:

```
  File ".../asyncio/base_events.py", line 2012, in _run_once
    event_list = self._selector.select(timeout)
  File ".../selectors.py", line 452, in select
    fd_event_list = self._selector.poll(timeout, max_ev)
  File "/home/wtthornton/code/tapps-mcp/packages/tapps-core/src/tapps_core/brain_bridge.py", line 3743, in _sigterm_drain_exit
    sys.exit(0)
    ~~~~~~~~^^^
SystemExit: 0

During handling of the above exception, another exception occurred:
...
asyncio.exceptions.CancelledError
```

(`nlt-build.log:381293-381311` and `:381586-381604` — the last such frame before each
restart marker; uvicorn dumps one copy per in-flight ASGI request, so the frame also
appears at `:381220`, `:381439`, `:381513`. The identical frame appears in
`nlt-memory.log`, `nlt-setup.log`, `nlt-project-docs.log`, `nlt-release-ship.log`, and
`nlt-linear-issues.log` at both events.)

Last normal activity before event 1: `nlt-build.log:380652`, `17:16:49Z` = 10:16:49 PDT,
followed by ordinary `200 OK` `/mcp` traffic. No error, no warning, no shutdown line.

## 4. Verdict

### 4.1 Why the deaths were silent — named, with file:line

`packages/tapps-core/src/tapps_core/brain_bridge.py:3742-3746` (pre-fix numbering; the frame the tracebacks name is `:3743`) installed a process-wide
SIGTERM handler whose entire body was `sys.exit(0)`. Three consequences, and together
they are the defect:

1. **Exit status 0.** A signalled death was byte-identical to a clean shutdown for any
   supervisor, parent, or human reading `$?`.
2. **No record that a signal arrived.** The handler logged nothing — not the signal
   number, not the time, not the pid. Nothing in the codebase wrote a death record.
3. **The only residue was incidental.** `sys.exit(0)` raises `SystemExit` on the main
   thread wherever the interpreter happens to be — here, mid-`selectors.poll()` inside
   the uvicorn event loop. Starlette/uvicorn then dump the traceback because the
   *lifespan* task got cancelled, not because anyone chose to report the death. That is
   why the surviving evidence is a `SystemExit: 0` stack rather than a log line.

Compounding it, the servers are unsupervised: `tapps-mcp-fleet.service` is
`Type=oneshot` + `RemainAfterExit=yes`, and `start_fleet` spawns each server with
`start_new_session=True` (`fleet_control.py:327-333`), so they live outside any systemd
cgroup with `Restart=`. systemd therefore has nothing to log when they die either. That
placement is deliberate (ADR-0024 — a oneshot would reap them on exit) and is not
changed here.

### 4.2 What killed them — bounded, not identified

**Mechanism: SIGTERM delivered to all six processes.** This is established, not
inferred: the `_sigterm_drain_exit` frame is only reachable from
`signal.signal(signal.SIGTERM, …)`.

**Sender: unrecoverable.** A Python signal handler receives no sender pid, the handler
recorded nothing, and the journals that would have carried the `systemctl`/session
correlation are rotated away (§2).

What the evidence *does* exclude:

- **Not OOM-kill.** The kernel OOM killer sends SIGKILL, which is uncatchable — it would
  leave no handler frame and no traceback, just an abrupt end of log.
- **Not an internal crash or unhandled exception.** Those surface their own traceback
  rooted in application code, not in a signal handler.
- **Not a resource/exit-code failure in the server itself.** Exit status was 0 by
  construction.

The residual class is **an external SIGTERM to the process group or session** — e.g. a
`tapps-mcp fleet stop`, a `systemctl --user restart tapps-mcp-fleet.service`, a
`pkill`-style sweep, or a session-scope teardown. The near-simultaneity of all six
(single second) is consistent with a group-wide delivery rather than six independent
events. Which of those it was cannot be established from surviving evidence, and this
document does not guess.

### 4.3 What makes the next death diagnosable

`brain_bridge.py` now writes a death record to fd 2 *before* unwinding —
`format_signal_exit_line` at
`packages/tapps-core/src/tapps_core/brain_bridge.py:3734`, called from the handler at
`:3768-3782`:

```
tapps.signal_exit signal=SIGTERM signum=15 pid=2968354 ppid=1 exit_status=0 uptime_s=931.4
```

Because the fleet routes both stdout and stderr into the per-server log
(`fleet_control.py:329-330`), this lands in `~/.tapps-mcp/fleet/logs/<server>.log` and is
greppable as `tapps.signal_exit`. `os.write` on an already-open descriptor is used rather
than `structlog`, whose lock can deadlock a handler that interrupted an in-flight emit.

The record carries the signal name/number, the dying pid, its **ppid**, and process
uptime. ppid plus uptime is what narrows "who" on the next occurrence — a reparented
`ppid=1` rules out an interactive shell ancestor; matching uptimes across all six
confirms group delivery. The sender pid itself is not obtainable from a Python signal
handler, and this is not claimed.

Second capture point: the watchdog now attaches evidence at *detection* time
(`_death_evidence`, `fleet_control.py:115-152`) — the recorded pid, whether it is still
alive, and the tail of the server's log. `tapps-mcp fleet ensure` prints it, so the
watchdog's own journal line carries the dead process's last words.

## 5. Worst-case death→automated-restart time

Arithmetic from the installed unit files and the debounce code, all read-only.

**Inputs**

| Quantity | Value | Source |
|---|---|---|
| Timer period | `OnUnitActiveSec=60`, `OnBootSec=45` | `~/.config/systemd/user/tapps-mcp-fleet-watch.timer`; generated at `fleet_control.py:739-740` |
| Measured period | **60.5 s** | 19 consecutive starts, 18:55:00 → 19:14:09 PDT 2026-08-26 (`journalctl --user -u tapps-mcp-fleet-watch.service`) |
| TCP probe | 3 attempts × 2.0 s timeout + 2 × 0.5 s backoff = **7.0 s**/port | `_port_persistently_down` + `_port_listening` (`fleet_control.py:453-470`, `:437`) |
| `/mcp` probe | 3 attempts × 3.0 s timeout + 2 × 0.5 s backoff = **10.0 s**/server | `_mcp_persistently_unresponsive` (`fleet_control.py:251-269`) |
| Debounce | restart on the **2nd** consecutive unhealthy poll | `ensure_fleet_running` (`fleet_control.py:491-583`, debounce at `:517-541`) |

**Poll duration when the fleet is unhealthy.** `_collect_unhealthy_servers` runs the
`/mcp` probe only for servers that passed TCP, so for *k* TCP-down servers the cost is
`7k + 10(6−k) = 60 − 3k`. It is maximised at `k = 0`:

- all six listening but handshake-hung → **D = 60.0 s** (worst case)
- all six processes gone → loopback refuses instantly, so only the backoffs count →
  **D ≈ 6.0 s** (realistic case)

**Timeline.** Worst case is a death immediately *after* a poll probed that server
healthy, so the full period is lost before detection even begins:

```
worst_case = D_residual + 2 × (60 s period + D_unhealthy) + T_bind
```

| Case | D_unhealthy | Detect (defer) | Confirm (restart issued) | + bind | Total |
|---|---|---|---|---|---|
| Worst (all hung, TCP up) | 60.0 s | 120.5 s | 240.5 s | ~3 s | **≈ 244 s (4.1 min)** |
| Realistic (all processes gone) | 6.0 s | 66.5 s | 132.5 s | ~3 s | **≈ 136 s (2.3 min)** |
| Floor (death just before a poll) | 6.0 s | 6.0 s | 72.5 s | ~3 s | **≈ 76 s (1.3 min)** |

**Cross-check against the incident.** Event 1: death ~10:22, restart marker 10:24:23 →
**143 s observed** against **136 s modelled** for the realistic case. The model holds.

**Reading.** The debounce costs a full poll interval by construction — that is its
purpose (a fleet-wide restart severs every client's HTTP session, so one bad poll must
not trigger one). Shrinking the poll interval is explicitly out of scope for TAP-6053.
The number to know operationally is **~2.3 min typical, ~4.1 min worst case**.

## 6. Fixes shipped with this document

| # | Acceptance | Where |
|---|---|---|
| 1 | Cause captured on the next death | `brain_bridge.py` `format_signal_exit_line` + handler; `fleet_control.py` `_death_evidence` |
| 2 | Unhealthy *reason* recorded per server (`tcp_down` vs `initialize_timeout`) | `fleet_control.py` `_collect_unhealthy_servers`, surfaced through `ensure_fleet_running` → `cli_fleet.py` `_format_unhealthy` |
| 3 | Manual `fleet ensure` can no longer starve confirmation | `fleet_control.py` `_watch_state_file` / `_read_watch_state` / `_write_watch_state`; `ensure_fleet_running(source=…)`; `cli_fleet.py --source` |
| 4 | Worst-case restart time measured | §5 |
| 5 | Regression tests | `packages/tapps-mcp/tests/unit/test_fleet_watchdog_debounce.py` |

### Why namespacing for #3

Before: a manual `tapps-mcp fleet ensure` wrote the **same**
`~/.tapps-mcp/fleet/.watch-unhealthy.json` the timer reads. A manual run that found the
fleet reachable cleared the pending set, so the next automated poll restarted its
two-strike count from zero — repeat that between every tick and confirmation never
lands, leaving a genuinely dead fleet down indefinitely.

Each caller now debounces in its own file: the timer keeps `.watch-unhealthy.json`
(passed explicitly as `fleet ensure --source watchdog` from the unit template), and any
other invocation gets `.watch-unhealthy-<source>.json`. Namespacing was chosen over
merging pending sets because it is **structural** — a manual run cannot reach the
automated state at all, so no interleaving of manual and automated runs can perturb it,
in either direction (it can neither reset the count nor short-circuit it). A merge rule
would still have to decide what a manual "healthy" observation means, and would leave
the two callers sharing one mutable object.

Upgrade safety: `_read_watch_state` still accepts the old bare-JSON-list format, so a
pending set written by an earlier build confirms on the next poll rather than being
dropped (covered by `test_legacy_list_state_still_confirms`). An installed unit that
predates the `--source watchdog` flag falls back to the `manual` namespace and keeps
identical two-strike behaviour there — no regression, and it self-corrects at the next
`fleet install-systemd`.

## 7. Follow-ups not taken here

- **Log rotation for `~/.tapps-mcp/fleet/logs/`.** These files are append-only and
  unbounded (72 MB for `nlt-build`). They are currently the *only* durable death record,
  so rotating them is a trade-off that needs its own decision, not a drive-by change.
- **Journal retention.** Default caps rotated away the 08-13 window. Raising
  `SystemMaxUse=`/`MaxRetentionSec=` is a host-config change, out of this repo's scope.
- **Supervising the servers directly** (so systemd records exit codes) would revisit
  ADR-0024 and is explicitly out of scope for TAP-6053.
