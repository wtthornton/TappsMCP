# TappsMCP — instructions for AI assistants

When the **TappsMCP** MCP server is configured in your host (Cursor, Claude Desktop, etc.), you have access to tools that provide **deterministic code quality checks, doc lookup, and domain expert advice**. Use them to avoid hallucinated APIs, missed quality steps, and inconsistent output.

---

## What TappsMCP is

TappsMCP is an MCP server that exposes tools for:

- **Scoring** Python files (0–100 across 7 categories)
- **Security scanning** (Bandit + secret detection)
- **Quality gates** (pass/fail vs presets)
- **Documentation lookup** (up-to-date library docs via Context7)
- **Config validation** (Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB)
- **Domain experts** (16 built-in experts with RAG-backed answers)
- **Session checklist** (track which tools were used so you don’t skip required steps)

You only see these tools when the host has started the TappsMCP server and attached it to your session.

---

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **tapps_server_info** | At **session start** — discover version, available tools, and installed checkers. Response includes a short `recommended_workflow` string. |
| **tapps_score_file** | When **editing or reviewing** a Python file. Use `quick=True` during edit–lint–fix loops; use full (default) **before declaring work complete**. |
| **tapps_security_scan** | When the change is **security-sensitive** or before a security-focused review. |
| **tapps_quality_gate** | **Before declaring work complete** — ensures the file passes the configured quality preset. Do not consider work done until this passes (or the user accepts the risk). |
| **tapps_lookup_docs** | **Before writing code** that uses an external library — use the returned docs to avoid hallucinated APIs. |
| **tapps_validate_config** | When **adding or changing** Dockerfile, docker-compose, or infra config. |
| **tapps_consult_expert** | When making **domain-specific decisions** (security, testing, APIs, database, etc.) and you want authoritative, RAG-backed guidance. |
| **tapps_list_experts** | When you need to see **which expert domains exist** before calling `tapps_consult_expert`. |
| **tapps_checklist** | **Before declaring work complete** — reports which tools were called and which are missing (with reasons). Fix missing required steps before saying done. |

---

## Recommended workflow

1. **Session start:** Call `tapps_server_info` (and optionally `tapps_list_experts` if you may need experts).
2. **Before using a library:** Call `tapps_lookup_docs(library=...)` and use the returned content when implementing.
3. **During edits:** Call `tapps_score_file(file_path=..., quick=True)` (and `fix=True` if you want ruff to apply fixes).
4. **Before declaring work complete:**  
   - Call `tapps_score_file(file_path=..., quick=False)` on changed files.  
   - Call `tapps_quality_gate(file_path=...)` — work is not done until it passes.  
   - Call `tapps_checklist(task_type=...)` and, if `complete` is false, call the missing required tools (use `missing_required_hints` for reasons).
5. **When in doubt:** Use `tapps_consult_expert` for domain-specific questions; use `tapps_validate_config` for Docker/infra files.

---

## Checklist task types

Use the `task_type` that best matches the current work:

- **feature** — New code
- **bugfix** — Fixing a bug
- **refactor** — Refactoring
- **security** — Security-focused change
- **review** — General code review (default)

The checklist uses this to decide which tools are required vs recommended vs optional for that task.
