"""Report assembly for the context-efficiency epic (SG0).

Runs every ``context_floor_*`` measurement and assembles the JSON report
shape ``measure_context_floor.py --json`` prints: the required top-level
integer keys plus a ``detail`` sub-object with per-bucket breakdowns.
"""

from __future__ import annotations

from typing import Any

from context_floor_core import _CLAUDE_MD, _REPO_ROOT, tokens
from context_floor_rules import RuleInfo, measure_claude_md, measure_rules
from context_floor_server import measure_server_instructions
from context_floor_session_start import measure_session_start
from context_floor_skills import SkillsResult, measure_skills
from context_floor_tools import ToolsResult, measure_tools


def tokens_from_bytes(byte_count: int) -> int:
    """``tokens()`` for a pre-computed byte count (avoids re-encoding text
    the caller already reduced to a byte total)."""
    return round(byte_count / 4)


def _tools_detail(tools_result: ToolsResult) -> dict[str, Any]:
    largest_tools = sorted(tools_result.tools, key=lambda t: -t.total_bytes)[:15]
    return {
        "docstrings_over_400_bytes": tools_result.docstrings_over_400_bytes,
        "total_tool_count": tools_result.tool_count,
        "largest_by_total_bytes": [
            {
                "name": t.name,
                "source_file": t.source_file,
                "docstring_bytes": t.docstring_bytes,
                "param_bytes": t.param_bytes,
                "total_bytes": t.total_bytes,
            }
            for t in largest_tools
        ],
    }


def _skills_detail(skills_result: SkillsResult) -> list[dict[str, Any]]:
    return [
        {
            "name": s.name,
            "description_bytes": s.description_bytes,
            "description_tokens": tokens(s.description),
            "context_fork": s.context_fork,
            "disable_model_invocation": s.disable_model_invocation,
        }
        for s in skills_result.skills
    ]


def _rules_detail(rules_detail: list[RuleInfo]) -> list[dict[str, Any]]:
    return [
        {
            "name": r.name,
            "bytes": r.byte_count,
            "always_loaded": r.always_loaded,
            "frontmatter_keys": r.frontmatter_keys,
            "always_apply_false": r.always_apply_false,
        }
        for r in rules_detail
    ]


def build_report() -> dict[str, Any]:
    tools_result = measure_tools()
    skills_result = measure_skills()
    rules_bytes, rules_detail = measure_rules()
    claude_md_bytes = measure_claude_md()
    server_instruction_tokens, server_instruction_detail = measure_server_instructions()
    session_start_result = measure_session_start()

    tool_docstring_tokens = tokens_from_bytes(tools_result.docstring_bytes)
    tool_param_tokens = tokens_from_bytes(tools_result.param_bytes)
    tool_schema_tokens = tool_docstring_tokens + tool_param_tokens
    skill_description_tokens = tokens_from_bytes(skills_result.description_bytes)
    always_loaded_rule_tokens = tokens_from_bytes(rules_bytes)
    claude_md_tokens = tokens_from_bytes(claude_md_bytes)
    session_start_tokens = session_start_result.static_tokens

    floor_tokens = (
        tool_schema_tokens
        + skill_description_tokens
        + always_loaded_rule_tokens
        + claude_md_tokens
        + server_instruction_tokens
        + session_start_tokens
    )

    return {
        "tool_schema_tokens": tool_schema_tokens,
        "tool_docstring_tokens": tool_docstring_tokens,
        "tool_param_tokens": tool_param_tokens,
        "tool_count": tools_result.tool_count,
        "skill_description_tokens": skill_description_tokens,
        "always_loaded_rule_tokens": always_loaded_rule_tokens,
        "claude_md_tokens": claude_md_tokens,
        "server_instruction_tokens": server_instruction_tokens,
        "session_start_tokens": session_start_tokens,
        "floor_tokens": floor_tokens,
        "detail": {
            "tools": _tools_detail(tools_result),
            "skills": _skills_detail(skills_result),
            "rules": _rules_detail(rules_detail),
            "server_instructions": server_instruction_detail,
            "session_start": {
                "static_bytes": session_start_result.static_bytes,
                "note": session_start_result.note,
                "fields": session_start_result.fields,
            },
            "claude_md": {
                "path": str(_CLAUDE_MD.relative_to(_REPO_ROOT)),
                "bytes": claude_md_bytes,
            },
        },
    }
