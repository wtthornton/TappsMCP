# Claude Code: Full Access Setup (No Permission Prompts)

This guide explains how to grant Claude Code **100% full access** so it never asks for permission when using tools (Bash, file read/write, MCP, etc.), including the "Allow this bash command?" dialogs in Cursor.

---

## Complete checklist (do both for 100% full access)

| Step | What | Where |
|------|------|--------|
| **1** | Set project bypass | Create or edit **`.claude/settings.local.json`** in the project root with `"defaultMode": "bypassPermissions"` (see below). |
| **2** | Set Cursor bypass | In **Cursor user** `settings.json`, set `"claudeCode.initialPermissionMode": "bypassPermissions"`. Paths: **Windows** `%APPDATA%\Cursor\User\settings.json` · **macOS** `~/Library/Application Support/Cursor/User/settings.json` · **Linux** `~/.config/Cursor/User/settings.json` |

Both steps are required: the project file controls Claude’s permission layer; the Cursor user setting stops Cursor from showing “Allow this bash command?” for terminal commands. No restart needed after changing either.

---

## Step 1: Project – `.claude/settings.local.json`

In the **project root** (same level as `README.md` and `docs/`), create a folder `.claude` if needed, then create or edit **`.claude/settings.local.json`**:

```json
{
  "defaultMode": "bypassPermissions"
}
```

With this, Claude Code skips permission prompts for tools in this workspace. You can keep or add a `permissions.allow` list; with `bypassPermissions`, the allowlist is ignored and Claude still has full access.

---

## Step 2: Cursor IDE – stop “Allow this bash command?”

Use **one** of these so Cursor does not prompt for bash/terminal commands:

- **Option A – Cursor user setting (recommended)**  
  Open Cursor **user** `settings.json` and set:
  ```json
  "claudeCode.initialPermissionMode": "bypassPermissions"
  ```
  Paths: **Windows** `%APPDATA%\Cursor\User\settings.json` · **macOS** `~/Library/Application Support/Cursor/User/settings.json` · **Linux** `~/.config/Cursor/User/settings.json`

- **Option B – When prompted**  
  When Cursor shows **“Allow this bash command?”**, choose **“Yes, allow [command] for this project (just you)”** to allow that command in this project from then on. You may need to do this per command type.

- **Option C – Auto-Run in UI**  
  **Settings → Cursor Settings → Agents → Auto-Run** → set **Auto-Run Mode** to **“Run Everything”**. The agent then runs all tools and terminal commands without asking.

---

## Verify it works

After both steps, run a command that would normally trigger a prompt (e.g. from the project root):

**Windows (cmd):**
```bat
cmd /c "dir /s /b . 2>nul | findstr /i plan"
```

**macOS/Linux:**
```bash
find . -type f -name "*plan*" 2>/dev/null | head -20
```

If the command runs and returns output (or “no match”) **without** a permission dialog, full access is working.

---

## Permission modes (reference)

| Mode               | Behavior |
|--------------------|----------|
| `default`          | Asks for permission on first use of each tool. |
| `acceptEdits`      | Auto-accepts file edits; may still prompt for other tools. |
| `plan`             | Read/analyze only; no file edits or command execution. |
| `bypassPermissions`| No prompts; full access to all tools. |

---

## Security note

**Use `bypassPermissions` only in environments you trust** (e.g. your own machine, known codebase). It disables permission checks; avoid it on shared or sensitive systems.

---

## File locations

| Item | Location |
|------|----------|
| Project config | `.claude/settings.local.json` (project root) |
| Cursor user settings | **Windows** `%APPDATA%\Cursor\User\settings.json` · **macOS** `~/Library/Application Support/Cursor/User/settings.json` · **Linux** `~/.config/Cursor/User/settings.json` |
| This guide | `docs/CLAUDE_FULL_ACCESS_SETUP.md` |

`.claude/settings.local.json` is typically gitignored so your choice stays local.
