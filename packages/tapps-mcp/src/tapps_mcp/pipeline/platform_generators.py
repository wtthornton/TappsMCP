"""Platform-specific generators for hooks, subagents, and skills.

Called from ``pipeline.init._setup_platform`` to create Claude Code and Cursor
configuration artifacts alongside the existing rule-file bootstrapping.

This module serves as a facade that re-exports all public API from the split
submodules. Import from here for backward compatibility.
"""

from __future__ import annotations

# Re-export generators from submodules for backward compatibility
from tapps_mcp.pipeline.platform_bundles import (
    generate_agent_teams_hooks,
    generate_ci_workflow,
    generate_claude_plugin_bundle,
    generate_claude_python_quality_rule,
    generate_cursor_plugin_bundle,
    generate_python_quality_rule,
    get_agent_teams_claude_md_section,
    get_ci_claude_md_section,
)

# Re-export hook templates (needed by upgrade tests that access _CLAUDE_HOOK_SCRIPTS)
from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_CLAUDE_MD_SECTION as _AGENT_TEAMS_CLAUDE_MD_SECTION,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_HOOK_SCRIPTS as _AGENT_TEAMS_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_HOOKS_CONFIG as _AGENT_TEAMS_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS as _CLAUDE_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS_BLOCKING as _CLAUDE_HOOK_SCRIPTS_BLOCKING,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS_BLOCKING_PS as _CLAUDE_HOOK_SCRIPTS_BLOCKING_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS_PS as _CLAUDE_HOOK_SCRIPTS_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOKS_CONFIG as _CLAUDE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOKS_CONFIG_PS as _CLAUDE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOK_SCRIPTS as _CURSOR_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOK_SCRIPTS_PS as _CURSOR_HOOK_SCRIPTS_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOKS_CONFIG as _CURSOR_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOKS_CONFIG_PS as _CURSOR_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    ENGAGEMENT_HOOK_EVENTS as _ENGAGEMENT_HOOK_EVENTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    PROMPT_HOOK_CONFIG as _PROMPT_HOOK_CONFIG,
)
from tapps_mcp.pipeline.platform_hooks import (
    generate_claude_hooks,
    generate_cursor_hooks,
    generate_memory_capture_hook,
)
from tapps_mcp.pipeline.platform_rules import (
    generate_bugbot_rules,
    generate_copilot_instructions,
    generate_cursor_rules,
)
from tapps_mcp.pipeline.platform_skills import generate_skills
from tapps_mcp.pipeline.platform_subagents import generate_subagent_definitions

# Re-export private names used by tests (backward compat)
__all__ = [
    "_AGENT_TEAMS_CLAUDE_MD_SECTION",
    "_AGENT_TEAMS_HOOKS_CONFIG",
    "_AGENT_TEAMS_HOOK_SCRIPTS",
    "_CLAUDE_HOOKS_CONFIG",
    "_CLAUDE_HOOKS_CONFIG_PS",
    "_CLAUDE_HOOK_SCRIPTS",
    "_CLAUDE_HOOK_SCRIPTS_BLOCKING",
    "_CLAUDE_HOOK_SCRIPTS_BLOCKING_PS",
    "_CLAUDE_HOOK_SCRIPTS_PS",
    "_CURSOR_HOOKS_CONFIG",
    "_CURSOR_HOOKS_CONFIG_PS",
    "_CURSOR_HOOK_SCRIPTS",
    "_CURSOR_HOOK_SCRIPTS_PS",
    "_ENGAGEMENT_HOOK_EVENTS",
    "_PROMPT_HOOK_CONFIG",
    "generate_agent_teams_hooks",
    "generate_bugbot_rules",
    "generate_ci_workflow",
    "generate_claude_hooks",
    "generate_claude_plugin_bundle",
    "generate_claude_python_quality_rule",
    "generate_copilot_instructions",
    "generate_cursor_hooks",
    "generate_cursor_plugin_bundle",
    "generate_cursor_rules",
    "generate_memory_capture_hook",
    "generate_python_quality_rule",
    "generate_skills",
    "generate_subagent_definitions",
    "get_agent_teams_claude_md_section",
    "get_ci_claude_md_section",
]
