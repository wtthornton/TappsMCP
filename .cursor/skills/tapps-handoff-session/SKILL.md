---
name: tapps-handoff-session
description: >-
  Write a structured cross-session handoff and close the TAPPS session
  lifecycle so the next chat can continue without a long paste. Use when
  ending a session, handing off to a fresh chat, or the user says hand
  off, save session state, or continue next time.
mcp_tools:
  - tapps_session_end
---

End the session with a durable handoff the next chat loads via `tapps-continue-session`.

1. **Draft handoff (5–10 bullets):** Done, Open, Next (P0), Blockers, Verify commands, Success criterion (one line).

2. **Persist (file is canonical).** Write or overwrite `.tapps-mcp/session-handoff.md`:

```markdown
# Session handoff
**Updated:** <ISO-8601 UTC>
**Linear P0:** <TAP-#### or none>

## Done
- ...

## Open
- ...

## Next (P0)
- ...

## Blockers
- ...

## Verify
- ...

## Success criterion
- ...
```

3. **Persist (brain, best-effort).** Run:
   `uv run tapps-mcp memory save --key session-handoff --tier context --tags handoff,cross-session --value "<plain-text bullets>"`
   Skip silently if brain is offline.

4. **Close lifecycle.** Call `tapps_session_end()`. Best-effort.

5. **Report.** `Handoff: .tapps-mcp/session-handoff.md. Linear P0: <id|none>. Next: tapps-continue-session`
