# Cursor / Electron Threading and Multi-CPU Usage — Verification

**Purpose:** Verify whether Cursor IDE can utilize multiple CPUs (multi-threading) for a single heavy task (e.g. AI agent, indexing).  
**Conclusion:** **Cursor does not multi-thread a single heavy task across multiple CPUs.** It is multi-**process** but each process is single-**threaded** for JavaScript work. One CPU-intensive task therefore runs on one core.

---

## 1. Architecture (Electron / VS Code base)

Cursor is built on **Electron** (Chromium + Node.js), same base as VS Code.

- **Main process:** One process per Cursor instance. Runs in **Node.js** with a **single-threaded event loop**. Handles app lifecycle, windows, system APIs.
- **Renderer process(es):** One per window (Chromium). UI and front-end JS; each renderer has a **single main JavaScript thread** for its work.
- **Extension host:** Separate Node.js process for extensions. Again **single-threaded** — one extension can monopolize the thread and block others.
- **Other processes:** Language servers (e.g. TypeScript), terminal PTY host, shared process, etc. Each is its own process but internally often single-threaded for the heavy JS/TS work.

So: **multiple OS processes** → the OS can schedule them on different cores. But **each process runs one main JS thread** for application logic.

---

## 2. Why a single task uses one CPU

- **Node.js event loop:** Single-threaded. One thread executes JavaScript; it can only run on **one CPU core at a time**.
- **Electron docs:** [Multithreading | Electron](https://www.electronjs.org/docs/latest/tutorial/multithreading) states that multi-threading is only available via **Web Workers** (opt-in, `nodeIntegrationInWorker`), with limits: native Node modules are not thread-safe; Electron built-in modules must not be used in workers.
- **VS Code / Cursor:** The main process and extension host do not offload heavy work to workers by default. So one heavy task (e.g. one AI agent run, or one extension’s work) runs on **one thread → one core**.

Result: **Cursor does not use multiple CPUs for a single heavy task.** It is not multi-threaded in that sense.

---

## 3. Multi-process vs multi-threaded

| Aspect | Cursor / Electron |
|--------|--------------------|
| **Multiple OS processes** | Yes (main, renderer(s), extension host, language servers, etc.). These can run on different cores. |
| **Multiple threads per process** | No for main/extension host/renderer JS. One main JS thread per process. |
| **Single heavy task (e.g. one agent)** | Runs on one thread → **one CPU**. |
| **Parallel agents (e.g. Cursor 2.0 “8 agents”)** | Task-level parallelism: 8 separate tasks/contexts; each still single-threaded, but 8 processes/contexts can be scheduled on different cores. |

So: **multi-process** can use multiple cores for *different* work; **multi-threaded** (one task spread across many cores) is **not** what Cursor does for a single agent or single heavy operation.

---

## 4. User-visible effects

- **Task Manager:** One Cursor “tree” can show many processes (main, renderer, helpers, extension host, etc.), so total Cursor CPU can be spread across a few cores. But a **single** intensive operation (e.g. one Composer/agent run) will not scale across 14+ cores; one process’s main thread will dominate one core.
- **Multiple windows:** Reports indicate all Cursor windows can **share the same main process**. So one window’s intensive work can block others — consistent with a single main thread handling all windows.
- **High CPU from one component:** Often attributed to the TypeScript/JS language server or extensions — each is a single-threaded process; it will peg **one** core when busy.

---

## 5. Sources

- Electron: [Process Model](https://www.electronjs.org/docs/latest/tutorial/process-model), [Multithreading](https://www.electronjs.org/docs/latest/tutorial/multithreading).
- Node.js: single-threaded event loop; one thread executes JS at a time.
- VS Code: three-process model (main, renderer, extension host); Extension Host described as single-threaded so one extension can monopolize it.
- Cursor forum: requests for “one process per window” and reports that one window’s heavy work freezes others.

---

## 6. Summary

- **Verified:** Cursor (Electron/Node/Chromium) does **not** multi-thread a single heavy task across multiple CPUs. Main process, extension host, and renderer JS are single-threaded; one intensive task uses **one core**.
- **Multi-process:** Multiple processes (main, renderers, extension host, language servers) can run on different cores, so *overall* Cursor can show usage on several cores, but not by splitting one agent/task across many threads.
- **Implication for TappsMCP:** MCP tools (e.g. scoring, validation) run in the TappsMCP server process (Python), which can use multiple threads/processes (e.g. `asyncio`, thread pool). Cursor’s own UI and agent orchestration remain single-threaded per process; the limitation is Cursor/Electron, not the MCP server.

---

## 7. Recommendations: Working Around Single-Thread Limits

### 7.1 Offload AI to a Separate Process (Recommended)

**Use Claude Code CLI in a terminal while keeping Cursor (or any editor) for editing.**

- **Cursor:** Use only for editing, search, and file navigation (light UI work).
- **Claude Code:** Run `claude` in a terminal in the same project. AI and tool calls (including TappsMCP) run in the **Claude Code process**, which is **separate** from Cursor.
- **Effect:** Editor and AI are different OS processes → the OS can schedule them on different cores. You get real multi-process parallelism (editor on one core, Claude on another) without changing Cursor’s internals.
- **TappsMCP:** Works with Claude Code via stdio MCP. Configure with `tapps-mcp init --host claude-code` or add the server to `~/.claude.json` / `.mcp.json`. See [TAPPS_MCP_SETUP_AND_USE.md](../../../TAPPS_MCP_SETUP_AND_USE.md) and [MCP_CLIENT_TIMEOUTS.md](../../../MCP_CLIENT_TIMEOUTS.md) for timeouts.

### 7.2 Use Cursor Only for Editing + Claude Code for AI (Hybrid)

- **Workflow:** Edit in Cursor; when you want AI (including TappsMCP quality tools), run Claude Code in an integrated or external terminal. No need to “use Claude instead of Cursor” for everything—use Cursor for the IDE and Claude Code for the agent.
- **Verify:** TappsMCP is documented and tested with Claude Code (stdio), Claude Desktop, and Cursor. Using Claude Code (CLI or desktop) with TappsMCP is supported and will work.

### 7.3 Reduce Single-Thread Load in Cursor

- **`.cursorignore`:** Exclude `node_modules`, `__pycache__`, `.git`, build outputs, and large data dirs so indexing and language tools do less work on the main thread.
- **Extensions:** Disable or remove unused extensions and language servers to free the extension host thread.
- **File size:** Keep files under ~1k lines where possible to reduce language server and parsing cost.

### 7.4 Use Cursor’s Parallel Agents (Cursor 2.0+)

- Run multiple agents in parallel (e.g. “8 agents”) for the same task. Each agent is a separate context; Cursor can schedule them across processes/cores. This is **task-level** parallelism, not one task using many cores, but it can increase total CPU use and improve result quality.

### 7.5 “Use Claude Directly Instead of Cursor” — Does It Help?

| Option | Multi-CPU / threading | TappsMCP | Notes |
|--------|------------------------|----------|--------|
| **Claude Code desktop app** | Same limitation: Electron/Node, single-threaded event loop per process. Claude Code has reported CPU issues (process accumulation, 100% CPU during multi-agent serialization, busy-wait). | Yes (stdio) | Does **not** avoid single-thread limits; different app, similar architecture. |
| **Claude Code in VS Code** | Same: VS Code is Electron; Claude Code extension runs in that process. Single-thread limits remain. | Yes (stdio) | Same as Cursor for threading. |
| **Claude Code CLI in terminal** | **Yes:** CLI runs as a **separate process**. Editor (Cursor or VS Code) + `claude` in terminal = two processes → can use two or more cores. | Yes (stdio) | **Best workaround** for “use multiple CPUs”: AI in one process, editor in another. |
| **Claude Desktop** | Electron app; single-thread limits similar to Cursor. Documented issues: multiple MCP server instances per server, process accumulation. | Yes (config in `claude_desktop_config.json`) | Works with TappsMCP but does not fix multi-thread limitation. |

**Conclusion:** Switching to “Claude directly” (desktop or VS Code) does **not** by itself give you multi-threading. Using **Claude Code CLI in a terminal** while keeping Cursor (or any editor) for editing **does** spread work across processes and thus across CPUs. TappsMCP works with Claude Code and Claude Desktop; verify timeouts (see MCP_CLIENT_TIMEOUTS.md) for long-running tools.
