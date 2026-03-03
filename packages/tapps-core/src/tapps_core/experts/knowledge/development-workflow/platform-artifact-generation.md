# Platform Artifact Generation

## Overview

Platform artifact generation produces configuration files, hooks, skills,
subagents, and rules tailored to specific AI coding assistants (Claude Code,
Cursor, VS Code Copilot). Artifacts are generated from templates that vary
by engagement level (high/medium/low) and adapt to the project's tech stack.

## Claude Code Skills

### Skill File Structure

Skills are markdown files in `.claude/skills/` with YAML frontmatter
specifying which MCP tools the skill is allowed to invoke:

```markdown
---
description: Score a Python file for quality issues
allowed-tools:
  - mcp__tapps-mcp__tapps_score_file
  - mcp__tapps-mcp__tapps_quick_check
---

# Score File

Run quality scoring on a Python file. Use `tapps_score_file` for full
analysis or `tapps_quick_check` for a fast ruff-only pass.

## Usage

Invoke with a file path: `/score src/app/main.py`
```

### Generating Skills Programmatically

```python
from pathlib import Path

def generate_skill(
    name: str,
    description: str,
    allowed_tools: list[str],
    body: str,
    output_dir: Path,
) -> Path:
    """Generate a Claude Code skill file with frontmatter."""
    frontmatter_tools = "\n".join(f"  - {t}" for t in allowed_tools)
    content = (
        f"---\n"
        f"description: {description}\n"
        f"allowed-tools:\n"
        f"{frontmatter_tools}\n"
        f"---\n\n"
        f"{body}\n"
    )
    skill_path = output_dir / f"{name}.md"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path
```

### Skill Naming Conventions

- Use lowercase kebab-case: `tapps-score`, `tapps-validate`, `tapps-research`
- Prefix with the server name for namespacing: `tapps-` for TappsMCP tools
- Keep descriptions under 100 characters for readability in tool listings

## Claude Code Subagents

### Subagent Configuration

Subagents are markdown files in `.claude/agents/` with YAML frontmatter
that defines MCP server access, turn limits, and permission mode:

```markdown
---
mcpServers:
  - tapps-mcp
maxTurns: 5
permissionMode: bypassPermissions
---

# Quality Watchdog

You are a quality watchdog agent. After each tool execution, check
if the changed files pass the quality gate.

## Responsibilities

1. Run `tapps_quick_check` on every modified Python file
2. Report any quality gate failures
3. Suggest fixes for common issues
```

### Permission Modes

| Mode | Use Case |
|---|---|
| `bypassPermissions` | Automated quality checks, read-only operations |
| `askUser` | Operations that modify files or run commands |
| `default` | Standard interactive mode |

Choose `bypassPermissions` for watchdog and validation agents that only
read and score files. Use `askUser` for agents that may edit code.

### maxTurns Guidance

- **3-5 turns**: Simple validation or scoring tasks
- **10-15 turns**: Multi-file analysis or refactoring assistance
- **25+ turns**: Complex feature implementation with quality checks

## Platform Rules

### Cursor Rules

Cursor rules live in `.cursor/rules/` as markdown files. They provide
instructions that Cursor's AI follows during code generation:

```markdown
# Quality Standards

When editing Python files in this project:

1. Run `tapps_quick_check` after every file edit
2. Ensure all files pass the quality gate before completing work
3. Use `tapps_validate_changed` before declaring work complete
```

### Claude Code Rules

Claude Code rules are generated as `.claude/rules/` markdown files
with optional path-scoping via frontmatter globs:

```markdown
---
globs:
  - "**/*.py"
---

# Python Quality Rules

After editing any Python file, run `tapps_quick_check` on the file.
Before declaring work complete, run `tapps_validate_changed` to check
all modified files against the quality gate.
```

### Path-Scoped Quality Rules

Path-scoped rules activate only when specific file patterns are involved:

```python
SCOPED_RULES = {
    "**/*.py": "Run tapps_quick_check after editing Python files.",
    "Dockerfile*": "Run tapps_validate_config on Dockerfile changes.",
    "docker-compose*.yml": "Run tapps_validate_config on compose changes.",
    "**/tests/**/*.py": "Ensure test files maintain coverage thresholds.",
}
```

This prevents quality rules from firing on non-Python file edits,
reducing noise and improving the developer experience.

## Hook Generation

### Hook Types

Claude Code supports several hook points for automation:

| Hook | Trigger | Common Use |
|---|---|---|
| `SessionStart` | Session begins | Run `tapps_session_start`, warm caches |
| `PreToolUse` | Before any tool call | Guard against destructive commands |
| `PostToolUse` | After a tool completes | Quality checks on changed files |
| `Stop` | Agent finishes a turn | Memory capture, progress summary |
| `TaskCompleted` | Task marked complete | Final validation, checklist |

### Hook File Structure

Hooks are defined in `.claude/hooks.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "tapps_report",
        "command": "bash .claude/hooks/post-tapps-report.sh"
      }
    ],
    "Stop": [
      {
        "command": "bash .claude/hooks/stop-memory-capture.sh"
      }
    ]
  }
}
```

### Hook Template Patterns

#### Bash Variant

```bash
#!/usr/bin/env bash
# Post-tool hook: read sidecar progress file
PROGRESS_FILE=".tapps-mcp/.validation-progress.json"
if [ -f "$PROGRESS_FILE" ]; then
    echo "Validation progress:"
    cat "$PROGRESS_FILE"
fi
```

#### PowerShell Variant

```powershell
# Post-tool hook: read sidecar progress file
$progressFile = ".tapps-mcp\.validation-progress.json"
if (Test-Path $progressFile) {
    Write-Host "Validation progress:"
    Get-Content $progressFile
}
```

Generate the appropriate variant based on the detected platform (Unix vs
Windows) during `tapps_init`.

## Engagement-Level Template Variants

### Three Levels

| Level | Enforcement | Description |
|---|---|---|
| **high** | Mandatory | All tools required; quality gate must pass |
| **medium** | Balanced | Core tools required, advanced tools recommended |
| **low** | Optional | Guidance only; no blocking requirements |

### Template Selection

Templates are stored as `agents_template_{level}.md` and
`platform_{platform}_{level}.md`. The loader selects based on the
configured engagement level:

```python
def load_template(platform: str, level: str) -> str:
    """Load the engagement-level-specific template."""
    template_name = f"platform_{platform}_{level}.md"
    template_path = PROMPTS_DIR / template_name
    return template_path.read_text(encoding="utf-8")
```

### Checklist Variations by Level

- **High**: `tapps_session_start`, `tapps_quick_check`, `tapps_validate_changed`,
  `tapps_checklist`, and `tapps_security_scan` are all required
- **Medium**: `tapps_session_start` and `tapps_quick_check` required;
  `tapps_validate_changed` and `tapps_checklist` recommended
- **Low**: All tools optional; guidance provided but not enforced

## AGENTS.md Smart-Merge

### Preserving Custom Sections

When updating AGENTS.md, smart-merge preserves user-added sections while
refreshing tool definitions and workflow instructions:

```python
def smart_merge_agents_md(
    existing: str,
    template: str,
) -> str:
    """Merge template updates into existing AGENTS.md.

    Preserves custom sections (those not in the template) while
    updating known sections with latest tool definitions.
    """
    existing_sections = parse_sections(existing)
    template_sections = parse_sections(template)

    merged: list[str] = []
    for name, content in template_sections.items():
        merged.append(content)  # Always use latest template

    # Append custom sections not in the template
    for name, content in existing_sections.items():
        if name not in template_sections:
            merged.append(content)

    return "\n\n".join(merged)
```

### Section Detection

Sections are identified by level-2 markdown headers (`## Section Name`).
Custom sections added by the user (e.g., `## Project-Specific Rules`) are
preserved across regeneration cycles.

## Best Practices

### Generation

1. **Always back up** existing files before overwriting during upgrades
2. **Detect platform** automatically rather than requiring explicit configuration
3. **Validate generated files** for correct YAML frontmatter syntax
4. **Use atomic writes** (write to temp file, then rename) to prevent corruption

### Hooks

1. **Keep hooks fast** - they run on every tool invocation
2. **Handle missing files gracefully** - sidecar files may not exist yet
3. **Log errors but don't block** - hook failures should not stop the agent

### Engagement Levels

1. **Start with medium** for new projects - balances quality and speed
2. **Use high** for production codebases with strict quality requirements
3. **Use low** for exploratory or prototyping work

## Anti-Patterns

1. **Hardcoded paths**: Use project-relative paths, not absolute paths
2. **Missing platform detection**: Always check OS before choosing shell variant
3. **Overwriting custom content**: Use smart-merge, never blindly replace AGENTS.md
4. **Ignoring engagement level**: A "high" config on a prototype creates friction
5. **Hooks that modify code**: Hooks should observe and report, not change files
