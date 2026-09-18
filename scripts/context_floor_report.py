"""Report assembly for the context-efficiency epic (SG0).

Runs every ``context_floor_*`` measurement and assembles the JSON report
shape ``measure_context_floor.py --json`` prints: the required top-level
integer keys plus a ``detail`` sub-object with per-bucket breakdowns.

TAP-7770: each bucket is measured independently. A bucket whose measurement
raises ``MeasurementError`` (e.g. the tools bucket hitting a registration it
cannot statically resolve to a single module-level definition) is recorded in
the top-level ``bucket_errors`` map and reported as failed in ``detail`` --
it never suppresses the buckets that succeeded. ``floor_tokens`` and the
per-bucket token fields for a failed bucket are ``None`` rather than a
silently wrong number.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from context_floor_core import _CLAUDE_MD, _REPO_ROOT, MeasurementError, tokens
from context_floor_rules import RuleInfo, measure_claude_md, measure_rules
from context_floor_server import measure_server_instructions
from context_floor_session_start import measure_session_start
from context_floor_skills import SkillsResult, measure_skills
from context_floor_tools import ToolsResult, measure_tools


def tokens_from_bytes(byte_count: int) -> int:
    """``tokens()`` for a pre-computed byte count (avoids re-encoding text
    the caller already reduced to a byte total)."""
    return round(byte_count / 4)


def _measure_bucket[T](name: str, fn: Callable[[], T], errors: dict[str, str]) -> T | None:
    """Run one bucket's measurement, recording a ``MeasurementError`` under
    *name* in *errors* instead of letting it abort the whole report."""
    try:
        return fn()
    except MeasurementError as exc:
        errors[name] = str(exc)
        return None


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
    errors: dict[str, str] = {}

    tools_result = _measure_bucket("tools", measure_tools, errors)
    skills_result = _measure_bucket("skills", measure_skills, errors)
    rules_measured = _measure_bucket("rules", measure_rules, errors)
    claude_md_bytes = _measure_bucket("claude_md", measure_claude_md, errors)
    server_measured = _measure_bucket("server_instructions", measure_server_instructions, errors)
    session_start_result = _measure_bucket("session_start", measure_session_start, errors)

    rules_bytes, rules_detail = rules_measured if rules_measured is not None else (None, None)
    server_instruction_tokens, server_instruction_detail = (
        server_measured if server_measured is not None else (None, None)
    )

    tool_docstring_tokens = (
        tokens_from_bytes(tools_result.docstring_bytes) if tools_result is not None else None
    )
    tool_param_tokens = (
        tokens_from_bytes(tools_result.param_bytes) if tools_result is not None else None
    )
    tool_schema_tokens = (
        tool_docstring_tokens + tool_param_tokens
        if tool_docstring_tokens is not None and tool_param_tokens is not None
        else None
    )
    skill_description_tokens = (
        tokens_from_bytes(skills_result.description_bytes) if skills_result is not None else None
    )
    always_loaded_rule_tokens = tokens_from_bytes(rules_bytes) if rules_bytes is not None else None
    claude_md_tokens = tokens_from_bytes(claude_md_bytes) if claude_md_bytes is not None else None
    session_start_tokens = (
        session_start_result.static_tokens if session_start_result is not None else None
    )

    bucket_totals = (
        tool_schema_tokens,
        skill_description_tokens,
        always_loaded_rule_tokens,
        claude_md_tokens,
        server_instruction_tokens,
        session_start_tokens,
    )
    floor_tokens: int | None = (
        sum(v for v in bucket_totals if v is not None)
        if all(v is not None for v in bucket_totals)
        else None
    )

    return {
        "tool_schema_tokens": tool_schema_tokens,
        "tool_docstring_tokens": tool_docstring_tokens,
        "tool_param_tokens": tool_param_tokens,
        "tool_count": tools_result.tool_count if tools_result is not None else None,
        "skill_description_tokens": skill_description_tokens,
        "always_loaded_rule_tokens": always_loaded_rule_tokens,
        "claude_md_tokens": claude_md_tokens,
        "server_instruction_tokens": server_instruction_tokens,
        "session_start_tokens": session_start_tokens,
        "floor_tokens": floor_tokens,
        "bucket_errors": errors,
        "detail": {
            "tools": (
                _tools_detail(tools_result)
                if tools_result is not None
                else {"error": errors["tools"]}
            ),
            "skills": (
                _skills_detail(skills_result)
                if skills_result is not None
                else {"error": errors["skills"]}
            ),
            "rules": (
                _rules_detail(rules_detail)
                if rules_detail is not None
                else {"error": errors["rules"]}
            ),
            "server_instructions": (
                server_instruction_detail
                if server_instruction_detail is not None
                else {"error": errors["server_instructions"]}
            ),
            "session_start": (
                {
                    "static_bytes": session_start_result.static_bytes,
                    "note": session_start_result.note,
                    "fields": session_start_result.fields,
                }
                if session_start_result is not None
                else {"error": errors["session_start"]}
            ),
            "claude_md": (
                {
                    "path": str(_CLAUDE_MD.relative_to(_REPO_ROOT)),
                    "bytes": claude_md_bytes,
                }
                if claude_md_bytes is not None
                else {"error": errors["claude_md"]}
            ),
        },
    }
