"""``tapps_skill_learnings`` tool handler for TappsMCP (TAP-6861).

Deterministic audit / promote / verify / trim over one skill directory's
``SKILL.md`` + ``learnings.md`` pair. All decision logic lives in
:mod:`tapps_mcp.pipeline.skill_learnings` and
:mod:`tapps_mcp.pipeline.skill_managed_block`; this module is I/O and
envelope-shaping only — read the two files, call the pure function, write
back only for the two actions that are explicit apply calls (``promote``,
``trim``). ``audit`` and ``verify`` never write.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import ToolAnnotations

from tapps_mcp.mcp_register import register_tool
from tapps_mcp.pipeline.skill_learnings import (
    TrimInstruction,
    apply_trim,
    audit,
    verify_single_home,
)
from tapps_mcp.pipeline.skill_managed_block import extract_block, promote_rule
from tapps_mcp.server_helpers import error_response, success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = structlog.get_logger(__name__)

_ANNOTATIONS_SKILL_LEARNINGS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

# TAP-1986: not a daily-driver tool — keep it out of the eager-loaded catalog.
_META_DEFERRED: dict[str, Any] = {"defer_loading": True}

_VALID_ACTIONS: frozenset[str] = frozenset({"audit", "promote", "verify", "trim"})
_VALID_TRIM_ACTIONS: frozenset[str] = frozenset({"delete", "keep_verbatim"})
SKILL_FILE_NAME = "SKILL.md"
LEARNINGS_FILE_NAME = "learnings.md"


def _load_skill_pair(skill_dir: str) -> tuple[str, str, Path, Path] | dict[str, Any]:
    """Return ``(skill_md, learnings_md, skill_path, learnings_path)`` or an error envelope."""
    directory = Path(skill_dir)
    skill_path = directory / SKILL_FILE_NAME
    learnings_path = directory / LEARNINGS_FILE_NAME
    if not skill_path.exists():
        return error_response(
            "tapps_skill_learnings",
            "skill_md_missing",
            f"{skill_path} does not exist.",
        )
    if not learnings_path.exists():
        return error_response(
            "tapps_skill_learnings",
            "learnings_md_missing",
            f"{learnings_path} does not exist.",
        )
    return (
        skill_path.read_text(encoding="utf-8"),
        learnings_path.read_text(encoding="utf-8"),
        skill_path,
        learnings_path,
    )


def _audit_action(skill_md: str, learnings_md: str) -> dict[str, Any]:
    report = audit(skill_md, learnings_md)
    return {
        "size": dataclasses.asdict(report.size),
        "already_covered": [dataclasses.asdict(f) for f in report.already_covered],
        "near_duplicate": [dataclasses.asdict(c) for c in report.near_duplicate],
        "contradictions": [dataclasses.asdict(c) for c in report.contradictions],
        "region": [dataclasses.asdict(f) for f in report.region],
    }


def _verify_action(rule_texts: str, skill_md: str, learnings_md: str) -> dict[str, Any]:
    rules = [line.strip() for line in rule_texts.splitlines() if line.strip()]
    if not rules:
        return error_response(
            "tapps_skill_learnings",
            "missing_rule_texts",
            "verify requires rule_texts (one rule per line).",
        )
    results = verify_single_home(rules, skill_md, learnings_md)
    return {"results": [dataclasses.asdict(r) for r in results]}


def _promote_action(
    rule_text: str, generator_file: str, skill_md: str, skill_path: Path
) -> dict[str, Any]:
    if not rule_text:
        return error_response(
            "tapps_skill_learnings", "missing_rule_text", "promote requires rule_text."
        )
    if not generator_file:
        return error_response(
            "tapps_skill_learnings",
            "missing_generator_file",
            "promote requires generator_file (the upstream generator that owns this skill's managed block).",
        )
    block = extract_block(skill_md)
    insertion_offset = skill_md.find(block) + len(block) if block is not None else len(skill_md)
    outcome = promote_rule(skill_md, insertion_offset, generator_file=generator_file)
    data = dataclasses.asdict(outcome)
    if outcome.accepted:
        updated = f"{skill_md[:insertion_offset]}\n\n- {rule_text}\n{skill_md[insertion_offset:]}"
        skill_path.write_text(updated, encoding="utf-8")
        data["written_to"] = str(skill_path)
    return data


def _parse_trim_plan(trim_plan_json: str) -> list[TrimInstruction] | dict[str, Any]:
    try:
        raw_plan = json.loads(trim_plan_json)
    except json.JSONDecodeError as exc:
        return error_response(
            "tapps_skill_learnings", "invalid_trim_plan", f"trim_plan_json is not valid JSON: {exc}"
        )
    if not isinstance(raw_plan, list) or not raw_plan:
        return error_response(
            "tapps_skill_learnings",
            "invalid_trim_plan",
            "trim_plan_json must be a non-empty JSON array of {content_hash, action} objects.",
        )
    instructions: list[TrimInstruction] = []
    for item in raw_plan:
        if (
            not isinstance(item, dict)
            or item.get("action") not in _VALID_TRIM_ACTIONS
            or not isinstance(item.get("content_hash"), str)
        ):
            return error_response(
                "tapps_skill_learnings",
                "invalid_trim_plan",
                f"each trim_plan_json entry needs a string content_hash and "
                f"action in {sorted(_VALID_TRIM_ACTIONS)}; got {item!r}.",
            )
        instructions.append(
            TrimInstruction(content_hash=item["content_hash"], action=item["action"])
        )
    return instructions


def _trim_action(trim_plan_json: str, learnings_md: str, learnings_path: Path) -> dict[str, Any]:
    if not trim_plan_json:
        return error_response(
            "tapps_skill_learnings", "missing_trim_plan", "trim requires trim_plan_json."
        )
    parsed = _parse_trim_plan(trim_plan_json)
    if isinstance(parsed, dict):
        return parsed
    outcome = apply_trim(learnings_md, parsed)
    data = dataclasses.asdict(outcome)
    if outcome.applied and outcome.updated_text is not None:
        learnings_path.write_text(outcome.updated_text, encoding="utf-8")
        data["written_to"] = str(learnings_path)
        del data["updated_text"]
    return data


async def tapps_skill_learnings(
    action: str,
    skill_dir: str = "",
    rule_text: str = "",
    rule_texts: str = "",
    generator_file: str = "",
    trim_plan_json: str = "",
) -> dict[str, Any]:
    """Deterministic audit / promote / verify / trim for a skill's learnings pair.

    Consolidates the drift between a skill's ``SKILL.md`` (managed-block +
    project-region) and its ``learnings.md`` (append-only log). Every
    verdict is derived from file bytes — no model call in the code path.
    Only ``promote`` and ``trim`` write; ``audit`` and ``verify`` are
    read-only.

    Args:
        action: One of ``"audit"`` (read-only report: size, already_covered,
            near_duplicate, contradictions, region), ``"promote"`` (guarded
            insertion of one rule into ``SKILL.md``), ``"verify"`` (single-
            home invariant check), or ``"trim"`` (content-hash-addressed,
            all-or-nothing deletion from ``learnings.md``).
        skill_dir: Path to the skill directory containing ``SKILL.md`` and
            ``learnings.md``. Required for every action.
        rule_text: The rule to promote. Required for ``action="promote"``.
        rule_texts: Newline-separated rule texts to check. Required for
            ``action="verify"``.
        generator_file: The upstream generator file that owns this skill's
            managed block (e.g. ``"pipeline/platform_skill_orchestration.py"``).
            Required for ``action="promote"`` — named in the refusal message
            when the destination is unsafe.
        trim_plan_json: JSON array of ``{"content_hash": ..., "action":
            "delete"|"keep_verbatim"}`` objects. Required for
            ``action="trim"``. Get hashes from a prior ``audit`` finding via
            ``bullet_content_hash`` — never a line number.
    """
    from tapps_mcp.server import _record_call, _record_execution

    start = time.perf_counter_ns()
    _record_call("tapps_skill_learnings")

    if action not in _VALID_ACTIONS:
        return error_response(
            "tapps_skill_learnings",
            "invalid_action",
            f"Invalid action {action!r}. Must be one of: {', '.join(sorted(_VALID_ACTIONS))}",
        )
    if not skill_dir:
        return error_response(
            "tapps_skill_learnings", "missing_skill_dir", "skill_dir is required."
        )

    loaded = _load_skill_pair(skill_dir)
    if isinstance(loaded, dict):
        data = loaded
    else:
        skill_md, learnings_md, skill_path, learnings_path = loaded
        if action == "audit":
            data = _audit_action(skill_md, learnings_md)
        elif action == "verify":
            data = _verify_action(rule_texts, skill_md, learnings_md)
        elif action == "promote":
            data = _promote_action(rule_text, generator_file, skill_md, skill_path)
        else:
            data = _trim_action(trim_plan_json, learnings_md, learnings_path)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    if "error" in data:
        _record_execution(
            "tapps_skill_learnings",
            start,
            status="failed",
            action=action,
            error_code=data["error"]["code"],
        )
        return data

    response = success_response("tapps_skill_learnings", elapsed_ms, data)
    _record_execution("tapps_skill_learnings", start, status="success", action=action)
    return response


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register the skill-learnings tool on the shared *mcp_instance* (Epic 79.1)."""
    if "tapps_skill_learnings" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_skill_learnings,
            annotations=_ANNOTATIONS_SKILL_LEARNINGS,
            meta=_META_DEFERRED,
        )
