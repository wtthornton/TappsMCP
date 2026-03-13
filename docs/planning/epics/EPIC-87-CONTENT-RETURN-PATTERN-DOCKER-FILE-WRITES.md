# Epic 87: Content-Return Pattern for Docker-Safe File Writes

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P0 - Critical
**Estimated LOE:** ~3-4 weeks (1 developer)
**Completed:** 2026-03-12
**Dependencies:** None (all prerequisite patterns already exist in docs-mcp generators)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this because TappsMCP and DocsMCP tools that write files directly to the host filesystem **fail inside Docker containers**. The Docker MCP Toolkit mounts workspaces with restricted permissions, causing `tapps_init`, `tapps_upgrade`, and all 13 DocsMCP generators to throw `Permission denied` when they attempt direct file writes. This is the #1 blocker for the Docker MCP distribution model.

Rather than fighting Docker's security model, we align with the emerging MCP best practice: **tools return file contents as structured output; the AI client writes the files using its own native capabilities**.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

All 24 file-writing MCP tools return structured `FileOperation` manifests that the AI client (Claude Code, Cursor, etc.) can apply using its native file-write capabilities. Tools detect their runtime environment (Docker vs local) and automatically choose between direct-write mode (local, backward-compatible) and content-return mode (Docker, safe). The upgrade/init skills and AGENTS.md provide clear instructions so LLMs reliably apply the returned file operations.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

### The Problem (Discovered 2026-03-12)

1. **Docker MCP Toolkit blocks host writes by default.** The [Docker MCP Toolkit docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/) state: *"MCP Servers have no access to the host filesystem. The user explicitly selects the servers that will be granted file mounts."* Even with volume mounts, container processes often lack write permissions.

2. **Local binary fallback is version-locked.** The standalone `tapps-mcp.exe` (PyInstaller binary) at `~/.local/bin/` is v0.8.5 while Docker runs v1.4.1. Template files added after v0.8.5 are missing.

3. **This affects every consuming project.** Any project using TappsMCP via Docker MCP (the recommended distribution) cannot run `tapps_init`, `tapps_upgrade`, or any DocsMCP generator with `output_path`.

### The Solution (Industry Best Practice)

Three patterns emerged from 2025-2026 MCP ecosystem research:

| Pattern | Description | When to Use |
|---|---|---|
| **Content-Return** | Tool returns file contents + metadata; AI client writes files | Default for Docker environments |
| **Filesystem Companion** | Delegate writes to `mcp/filesystem` server in same profile | Alternative for non-AI clients |
| **Local Direct-Write** | Tool writes files directly (current behavior) | When running on host via `uv run` or `uvx` |

**Pattern 1 (Content-Return) is the primary fix** because:
- It works with every MCP client (Claude Code, Cursor, VS Code Copilot)
- The [MCP spec (2025-11-25)](https://modelcontextprotocol.io/specification/draft/server/tools) supports `structuredContent` + `outputSchema` for exactly this
- [Anthropic's tool design guide](https://www.anthropic.com/engineering/writing-tools-for-agents) recommends returning actionable structured data over side effects
- docs-mcp generators already implement this pattern (return content when `output_path` is empty)
- The AI client already has file-write tools (Write, Edit) with proper permissions

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

### Core Pattern
- [x] New `FileOperation` schema defined: `{path, content, mode, encoding, description}`
- [x] All 24 file-writing tools support content-return mode
- [x] Tools auto-detect Docker environment (`TAPPS_DOCKER=1` or read-only filesystem probe)
- [x] In Docker mode: tools return `FileOperation[]` manifest instead of writing
- [x] In local mode: tools write files directly (backward-compatible, no behavior change)
- [x] `outputSchema` declared on all tools that can return `FileOperation[]`

### Agent Instructions
- [x] AGENTS.md updated with "Applying File Operations" section
- [x] Skills (`tapps-init`, `tapps-upgrade`) include file-apply instructions
- [x] `structuredContent` includes `agent_instructions` field with persona, tool guidance, and verification steps
- [x] Instructions work for Claude Code, Cursor, and VS Code Copilot

### Testing & Validation
- [x] Unit tests for all 24 tools in both modes (Docker and local)
- [x] Integration test: mock Docker environment, verify no file writes occur
- [x] Integration test: verify returned manifest matches expected file contents
- [x] Existing tests continue to pass (backward compatibility)

<!-- docsmcp:end:acceptance-criteria -->

---

## Research Findings: What Makes This Pattern Work for LLMs

### The `FileOperation` Schema

Based on [MCP structured content spec](https://modelcontextprotocol.io/specification/draft/server/tools), [Anthropic's tool design guide](https://www.anthropic.com/engineering/writing-tools-for-agents), and testing across Claude Code and Cursor:

```json
{
  "type": "object",
  "properties": {
    "files": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Relative path from project root (forward slashes)"
          },
          "content": {
            "type": "string",
            "description": "Full file content to write"
          },
          "mode": {
            "type": "string",
            "enum": ["create", "overwrite", "merge"],
            "description": "create=new file only, overwrite=replace, merge=smart-merge with existing"
          },
          "encoding": {
            "type": "string",
            "default": "utf-8"
          },
          "description": {
            "type": "string",
            "description": "Human-readable explanation of what this file does and why"
          },
          "priority": {
            "type": "integer",
            "description": "Write order (1=first). Files with dependencies should have higher numbers"
          }
        },
        "required": ["path", "content", "mode"]
      }
    },
    "agent_instructions": {
      "type": "object",
      "properties": {
        "persona": {
          "type": "string",
          "description": "Role the agent should adopt when applying these files"
        },
        "tool_preference": {
          "type": "string",
          "description": "Which tool to use for writing (Write for new files, Edit for merges)"
        },
        "verification_steps": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Steps to verify after all files are written"
        },
        "warnings": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Important caveats the agent should communicate to the user"
        }
      }
    },
    "summary": {
      "type": "string",
      "description": "One-line summary of all file operations for the agent to relay to the user"
    },
    "source_version": {
      "type": "string",
      "description": "TappsMCP/DocsMCP version that generated these files"
    }
  }
}
```

### Why `agent_instructions` Is Critical

LLMs consuming tool output need explicit guidance to apply file operations correctly. Without it, agents may:
- Write files in the wrong order (hooks before the config they depend on)
- Use `Edit` when they should use `Write` (or vice versa)
- Skip verification steps
- Not communicate important context to the user

The `agent_instructions` field provides:

| Field | Purpose | Example |
|---|---|---|
| `persona` | Sets the agent's mindset for this task | `"You are a project scaffolding assistant. Write each file exactly as provided -- do not modify content, add comments, or reformat."` |
| `tool_preference` | Tells the agent which write tool to use | `"Use the Write tool for mode=create and mode=overwrite. Use the Edit tool for mode=merge, matching the existing content as old_string."` |
| `verification_steps` | Post-write checklist | `["Verify AGENTS.md exists at project root", "Run 'git diff' to show the user what changed", "Remind user to review hooks before committing"]` |
| `warnings` | Important caveats | `["Hook scripts require execute permission on Unix (chmod +x)", "CLAUDE.md contains project-specific instructions -- review before committing"]` |

### Example Tool Response (Docker Mode)

```json
{
  "tool": "tapps_upgrade",
  "success": true,
  "data": {
    "mode": "content_return",
    "reason": "Docker container detected -- returning file contents for client-side application",
    "backup_recommended": true,
    "files": [
      {
        "path": "AGENTS.md",
        "content": "# AGENTS.md\n\nThis file provides guidance...",
        "mode": "overwrite",
        "description": "Updated AGENTS.md with latest tool descriptions and workflow guidance",
        "priority": 1
      },
      {
        "path": ".claude/hooks/tapps-pre-edit.sh",
        "content": "#!/bin/bash\n# TappsMCP pre-edit hook...",
        "mode": "create",
        "description": "Pre-edit hook that runs tapps_quick_check before file modifications",
        "priority": 2
      }
    ],
    "agent_instructions": {
      "persona": "You are a project scaffolding assistant applying TappsMCP configuration files. Write each file exactly as provided without modification. Preserve file content byte-for-byte -- do not add comments, reformat, or 'improve' the generated content.",
      "tool_preference": "Use the Write tool for all files with mode 'create' or 'overwrite'. For files with mode 'merge', read the existing file first, then use the Edit tool to apply changes. Process files in priority order (lowest number first).",
      "verification_steps": [
        "After writing all files, run 'git status' to show the user what was created/modified",
        "List any files with mode 'create' that already existed (warn user of overwrite)",
        "On Unix/macOS: remind user to run 'chmod +x' on any .sh files in .claude/hooks/"
      ],
      "warnings": [
        "CLAUDE.md and AGENTS.md may contain project-specific customizations -- the 'merge' mode preserves user sections",
        "Hook scripts must have execute permission on Unix systems",
        "Review all generated files before committing to version control"
      ]
    },
    "summary": "TappsMCP upgrade v1.4.1: 12 files to write (3 new, 9 updated). Includes AGENTS.md, platform rules, 4 hooks, 3 skills, 2 agents.",
    "source_version": "1.4.1"
  }
}
```

### Example Tool Response (Local/Direct-Write Mode)

```json
{
  "tool": "tapps_upgrade",
  "success": true,
  "data": {
    "mode": "direct_write",
    "backup": ".tapps-mcp/backups/2026-03-12-114933",
    "components": {
      "agents_md": {"action": "updated"},
      "hooks": {"scripts_created": ["tapps-pre-edit.sh", "tapps-post-edit.sh"]},
      "platforms": [{"host": "claude-code", "components": {"mcp_config": "ok"}}]
    },
    "summary": "TappsMCP upgrade v1.4.1 complete. 12 files written. Backup at .tapps-mcp/backups/2026-03-12-114933"
  }
}
```

---

<!-- docsmcp:start:stories -->
## Stories

### [87.1] -- FileOperation Schema & Environment Detection (COMPLETE)

**Points:** 5

Define the `FileOperation` Pydantic model and Docker environment detection utility used by all subsequent stories.

**Tasks:**
- [x] Create `packages/tapps-core/src/tapps_core/common/file_operations.py` with `FileOperation`, `FileManifest`, `AgentInstructions` Pydantic models
- [x] Add `detect_write_mode()` function: checks `TAPPS_DOCKER` env var, then falls back to tempfile write probe
- [x] Add `WriteMode` enum: `DIRECT_WRITE`, `CONTENT_RETURN`
- [x] Add `FileManifest.to_structured_content()` method for MCP `structuredContent` serialization
- [x] Add `FileManifest.to_text_content()` method for backward-compatible `content` text block
- [x] Unit tests for all models, serialization, and environment detection (mock env vars, mock read-only fs)
- [x] Export from `tapps_core.common` and re-export via `tapps_mcp.common` for backward compat

**Definition of Done:** FileOperation schema is defined, environment detection works in both Docker and local modes, and all models serialize correctly for MCP structured content.

---

### [87.2] -- tapps_init Content-Return Mode (COMPLETE)

**Points:** 8

Update `tapps_init` / `bootstrap_pipeline()` to return a `FileManifest` when running in Docker mode instead of writing files directly.

**Tasks:**
- [x] Modify `_BootstrapState` to accumulate `FileOperation` objects alongside `created`/`skipped` lists
- [x] In `safe_write()` and `safe_write_or_overwrite()`: when `write_mode == CONTENT_RETURN`, append to `FileOperation` list instead of calling `.write_text()`
- [x] Generate `agent_instructions` with persona: *"You are a project scaffolding assistant setting up TappsMCP for the first time..."*
- [x] Include `tool_preference`: *"Use the Write tool for all files. These are all new files in a fresh project setup."*
- [x] Include `verification_steps`: check AGENTS.md exists, verify .tapps-mcp.yaml, remind about hook permissions
- [x] Include `warnings`: list files that contain project-specific config the user should review
- [x] Set `priority` on each file: config files first (1), then AGENTS.md (2), then platform rules (3), then hooks/skills/agents (4)
- [x] Update `server_pipeline_tools.py` handler to include `structuredContent` in response when content-return mode is used
- [x] Add `output_mode` parameter to `tapps_init` tool: `"auto"` (default, detect), `"content_return"`, `"direct_write"`
- [x] Update existing dry_run tests; add new tests for content-return mode
- [x] Verify backward compatibility: local mode produces identical output to current behavior

**Definition of Done:** `tapps_init` returns a complete file manifest in Docker mode that an AI agent can apply to fully bootstrap a project. Local mode behavior is unchanged.

---

### [87.3] -- tapps_upgrade Content-Return Mode (COMPLETE)

**Points:** 8

Update `tapps_upgrade` / `upgrade_pipeline()` to return a `FileManifest` when running in Docker mode.

**Tasks:**
- [x] Modify `upgrade_pipeline()` to use `detect_write_mode()` and accumulate `FileOperation` objects
- [x] Handle `mode="merge"` for AGENTS.md (existing content must be preserved/merged)
- [x] For merge operations: include both the `content` (new version) and a `merge_base` field (template sections that can be replaced while preserving user sections)
- [x] Generate `agent_instructions` with persona: *"You are a project upgrade assistant updating TappsMCP scaffolding to the latest version..."*
- [x] Include `tool_preference`: *"Use Write for mode 'create'/'overwrite'. For mode 'merge', read the existing file first, identify TappsMCP-managed sections (marked with <!-- tapps:start --> / <!-- tapps:end --> comments), and replace only those sections using Edit."*
- [x] Include `verification_steps`: run `git diff` to review, check no user customizations were lost
- [x] Include `warnings`: *"Backup your project before applying. Run 'git stash' if you have uncommitted changes."*
- [x] Skip backup creation in content-return mode (client-side concern)
- [x] Add `output_mode` parameter to `tapps_upgrade` tool
- [x] Tests for content-return mode with various upgrade scenarios (fresh install, minor update, major version change)

**Definition of Done:** `tapps_upgrade` returns a file manifest in Docker mode. Merge operations include enough context for the AI agent to correctly merge managed sections while preserving user customizations.

---

### [87.4] -- DocsMCP Generators Content-Return Unification (COMPLETE)

**Points:** 5

Standardize all 13 DocsMCP generator tools to use the `FileOperation` schema when returning content. Currently they return `{"content": "..."}` -- this story adds the `FileManifest` wrapper with `agent_instructions`.

**Tasks:**
- [x] Import `FileOperation`, `FileManifest` into docs-mcp (from tapps-core or vendored copy)
- [x] Update all 13 generator tools: when `output_path` is empty AND Docker is detected, return `FileManifest` with `agent_instructions`
- [x] When `output_path` is provided in local mode: keep current direct-write behavior
- [x] Add tool-specific `agent_instructions` for each generator:
  - `docs_generate_readme`: persona = *"Technical writer creating project README"*, tool_preference = *"Write to README.md at project root"*, verification = *"Verify links in README resolve correctly"*
  - `docs_generate_changelog`: persona = *"Release manager updating changelog"*, warning = *"Ensure entries are in reverse chronological order"*
  - `docs_generate_api`: persona = *"API documentation specialist"*, tool_preference = *"Create docs/api/ directory first, then write individual files"*
  - (Similar for remaining 10 generators)
- [x] Update `success_response()` helper to include `structuredContent` field when `FileManifest` is present
- [x] Tests for all 13 generators in content-return mode

**Definition of Done:** All 13 DocsMCP generators return standardized `FileManifest` responses with tool-specific agent instructions when running in Docker.

---

### [87.5] -- Tier 3 Tools: Config & State Writers (COMPLETE)

**Points:** 5

Update `tapps_manage_experts`, `tapps_set_engagement_level`, `tapps_memory` (export), and `docs_config` to support content-return mode.

**Tasks:**
- [x] `tapps_manage_experts` (scaffold action): return `FileManifest` with expert knowledge file templates
- [x] `tapps_set_engagement_level`: return `FileManifest` with updated `.tapps-mcp.yaml` content
- [x] `tapps_memory` (export action): return export JSON in `FileManifest` instead of writing to disk
- [x] `docs_config` (set action): return `FileManifest` with updated `.docsmcp.yaml`
- [x] Agent instructions for config tools: persona = *"Configuration assistant"*, warning = *"Config files affect all subsequent tool behavior -- verify values before writing"*
- [x] Tests for all 4 tools in content-return mode

**Definition of Done:** All Tier 3 tools return file manifests in Docker mode. Config changes are clearly communicated to the agent with appropriate warnings.

---

### [87.6] -- Skills & AGENTS.md: Agent Guidance for File Application (COMPLETE)

**Points:** 5

Update the scaffolding skills, AGENTS.md template, and CLAUDE.md guidance so that AI agents consuming TappsMCP know how to handle `FileManifest` responses.

**Tasks:**
- [x] Update `tapps-init` skill (`.claude/skills/tapps-init.md`):
  - Add instruction block: *"When tapps_init returns a FileManifest (mode: content_return), apply all files in priority order using the Write tool. Do not modify file contents."*
  - Add example workflow showing the full init-then-apply cycle
- [x] Update `tapps-upgrade` skill (`.claude/skills/tapps-upgrade.md`):
  - Add merge instruction: *"For files with mode 'merge', read the existing file, locate <!-- tapps:start --> / <!-- tapps:end --> markers, and replace only the managed sections using Edit."*
  - Add backup instruction: *"Before applying, create a git stash or commit current state."*
- [x] Update AGENTS.md template (`distribution/templates/agents_template_*.md`):
  - Add "Applying File Operations from TappsMCP" section explaining the pattern
  - Include the `FileOperation` schema reference
  - Document the `agent_instructions` contract
- [x] Update CLAUDE.md in TappsMCP repo with the pattern documentation
- [x] Add `tapps-apply-files` skill that can be invoked after any tool returns a `FileManifest`:
  ```
  /tapps-apply-files
  # Reads the last FileManifest from conversation context
  # Applies files in priority order
  # Runs verification steps
  # Reports results to user
  ```

**Definition of Done:** An AI agent using TappsMCP via Docker can successfully bootstrap a new project end-to-end by calling `tapps_init` and then following the returned `agent_instructions` to write all files.

---

### [87.7] -- Integration Testing & Docker Validation (COMPLETE)

**Points:** 3

End-to-end validation that the full pattern works in a real Docker MCP environment.

**Tasks:**
- [x] Create integration test script that builds Docker image, runs `tapps_init` via MCP, and verifies `FileManifest` is returned (not file writes)
- [x] Create integration test for `tapps_upgrade` in Docker
- [x] Test with Claude Code: invoke `tapps_init` via Docker MCP, verify agent applies files correctly
- [x] Test with Cursor: same flow via Docker MCP
- [x] Verify the `output_mode=direct_write` override works when user explicitly wants Docker to write (e.g., with writable mount)
- [x] Performance test: verify content-return mode is not significantly slower than direct-write
- [x] Update `docker-mcp/README.md` with the content-return pattern documentation
- [x] Update `tapps_doctor` to detect Docker environment and report write capability

**Definition of Done:** The content-return pattern is validated in real Docker MCP environments with both Claude Code and Cursor. Documentation is updated.

<!-- docsmcp:end:stories -->

---

## Technical Design

### Environment Detection Logic

```python
from __future__ import annotations

import os
import tempfile
from enum import Enum
from pathlib import Path


class WriteMode(Enum):
    DIRECT_WRITE = "direct_write"
    CONTENT_RETURN = "content_return"


def detect_write_mode(project_root: Path) -> WriteMode:
    """Detect whether we can write to the project root."""
    # Explicit override via env var
    if os.environ.get("TAPPS_WRITE_MODE") == "direct":
        return WriteMode.DIRECT_WRITE
    if os.environ.get("TAPPS_WRITE_MODE") == "content":
        return WriteMode.CONTENT_RETURN

    # Docker environment detection
    if os.environ.get("TAPPS_DOCKER") == "1":
        # Still probe -- Docker might have writable mount
        pass

    # Filesystem write probe (same pattern as existing read-only detection)
    try:
        with tempfile.NamedTemporaryFile(
            dir=project_root, prefix=".tapps-write-test-", delete=True
        ):
            return WriteMode.DIRECT_WRITE
    except OSError:
        return WriteMode.CONTENT_RETURN
```

### Agent Instructions Best Practices (From Research)

Based on [Anthropic's tool design guide](https://www.anthropic.com/engineering/writing-tools-for-agents) and [Claude Code best practices](https://code.claude.com/docs):

1. **Persona sets the frame.** Telling the agent *"You are a project scaffolding assistant"* prevents it from improvising, adding docstrings, or "improving" generated content. Without a persona, agents frequently modify file contents.

2. **Tool preference eliminates ambiguity.** Agents have multiple write tools (Write, Edit, Bash with echo/cat). Specifying *"Use the Write tool"* prevents agents from using `echo > file` or other error-prone alternatives.

3. **Priority ordering prevents dependency errors.** Config files must exist before hooks that reference them. Numbering files by priority ensures correct write order.

4. **Verification steps close the loop.** Without explicit verification, agents often write files and move on without confirming success. Steps like *"Run git status to show the user what changed"* ensure the user sees results.

5. **Warnings prevent silent mistakes.** Agents won't know that `.sh` files need `chmod +x` on Unix unless told. They won't know that AGENTS.md has user-customized sections unless warned.

6. **Return content verbatim.** The `content` field must be the exact bytes to write. Agents should be instructed to write content *"byte-for-byte without modification"* -- otherwise they may reformat YAML, add trailing newlines, or "fix" intentional formatting.

7. **Summary enables user communication.** The `summary` field gives the agent a natural-language sentence to relay to the user: *"TappsMCP upgrade: 12 files to write (3 new, 9 updated)"*.

### Backward Compatibility

| Scenario | Behavior |
|---|---|
| Local `uv run tapps-mcp upgrade` | Direct-write (unchanged) |
| Docker MCP with writable mount + `TAPPS_WRITE_MODE=direct` | Direct-write (unchanged) |
| Docker MCP without writable mount | Content-return (new) |
| Docker MCP with read-only mount | Content-return (new) |
| `dry_run=True` (any environment) | Preview only, no writes, no content-return (unchanged) |
| `output_mode="content_return"` (any environment) | Content-return (explicit override) |

### Migration Path

1. **v1.5.0**: Add `FileOperation` schema, update `tapps_init` and `tapps_upgrade` (Stories 87.1-87.3)
2. **v1.5.1**: Update DocsMCP generators (Story 87.4)
3. **v1.6.0**: Update Tier 3 tools, skills, AGENTS.md (Stories 87.5-87.6)
4. **v1.6.1**: Integration testing and Docker validation (Story 87.7)

---

## Sources

- [Docker MCP Toolkit Docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/) -- "MCP Servers have no access to the host filesystem"
- [MCP Tools Specification (draft)](https://modelcontextprotocol.io/specification/draft/server/tools) -- `structuredContent` and `outputSchema`
- [MCP outputSchema RFC #356](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/356) -- Design discussion
- [Anthropic: Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents) -- Tool output best practices
- [Claude Code Best Practices](https://code.claude.com/docs) -- Agent workflow patterns
- [Cisco: What's New in MCP](https://blogs.cisco.com/developer/whats-new-in-mcp-elicitation-structured-content-and-oauth-enhancements) -- Structured content overview
- [MCP structuredContent Clarification Issue #1624](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1624) -- content vs structuredContent guidance
- [Stacklok MCP Filesystem Guide](https://docs.stacklok.com/toolhive/guides-mcp/filesystem) -- Read-only enforcement patterns
- [Docker MCP Blog](https://www.docker.com/blog/mcp-toolkit-mcp-servers-that-just-work/) -- MCP Toolkit architecture
