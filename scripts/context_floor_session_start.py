"""``tapps_session_start`` static-skeleton measurement (SG0, context-efficiency epic).

Sums the byte cost of the unconditional, environment-independent literal
content ``tapps_session_start(quick=False)`` embeds in its response --
deliberately a conservative floor, not the true per-session payload. See
``SessionStartResult.note`` for the full rationale (why not a live call, what
is excluded).
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from context_floor_core import (
    _TAPPS_CORE_SRC,
    _TAPPS_MCP_SRC,
    _TOOLS_DIR,
    MeasurementError,
    _assign_target,
    _dict_value_node,
    _find_function,
    _find_return_dict,
    _literal_dict_value,
    _parse,
    tokens,
)

_DEVELOPER_WORKFLOW = _TAPPS_MCP_SRC / "tapps_mcp" / "common" / "developer_workflow.py"
_SESSION_START_HELPERS = _TOOLS_DIR / "session_start_helpers.py"
_SESSION_START_CORE = _TOOLS_DIR / "session_start_core.py"
_SERVER_PY = _TAPPS_MCP_SRC / "tapps_mcp" / "server.py"
_PIPELINE_MODELS = _TAPPS_CORE_SRC / "tapps_core" / "common" / "pipeline_models.py"


def _module_constant(path: Path, name: str) -> Any:
    for node in _parse(path).body:
        target, value = _assign_target(node)
        if target == name:
            return ast.literal_eval(value) if value is not None else None
    raise MeasurementError(f"constant {name!r} not found in {path}")


def _collect_enum_string_values(class_node: ast.ClassDef) -> dict[str, str]:
    """Map ``MEMBER -> "value"`` for a ``StrEnum``'s simple ``MEMBER = "value"`` members."""
    values: dict[str, str] = {}
    for stmt in class_node.body:
        member_name, member_value = _assign_target(stmt)
        if (
            member_name
            and isinstance(member_value, ast.Constant)
            and isinstance(member_value.value, str)
        ):
            values[member_name] = member_value.value
    return values


def _collect_stage_tools_mapping(
    stage_tools_node: ast.Dict, stage_values: dict[str, str]
) -> tuple[list[str], dict[str, list[str]]]:
    """Resolve a ``{PipelineStage.X: [...]}`` dict literal's ``PipelineStage``
    member keys to their string values, in declaration order."""
    order: list[str] = []
    stage_tools: dict[str, list[str]] = {}
    for key, value in zip(stage_tools_node.keys, stage_tools_node.values, strict=True):
        if not (
            isinstance(key, ast.Attribute)
            and isinstance(key.value, ast.Name)
            and key.value.id == "PipelineStage"
        ):
            continue
        stage_name = stage_values.get(key.attr)
        if stage_name is None:
            raise MeasurementError(f"unknown PipelineStage member: {key.attr}")
        order.append(stage_name)
        stage_tools[stage_name] = ast.literal_eval(value)
    return order, stage_tools


def _parse_pipeline_stage_tools(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Resolve tapps-core's ``PipelineStage`` enum + ``STAGE_TOOLS`` dict --
    fully static configuration (fixed pipeline stages and their allowed
    tools), just expressed via an enum and a comprehension in the real
    server_info builder rather than as directly literal-evaluable values.
    """
    if not path.exists():
        raise MeasurementError(f"pipeline stage module not found: {path}")
    tree = _parse(path)
    stage_values: dict[str, str] = {}
    stage_tools_node: ast.Dict | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "PipelineStage":
            stage_values = _collect_enum_string_values(node)
        target, value = _assign_target(node)
        if target == "STAGE_TOOLS" and isinstance(value, ast.Dict):
            stage_tools_node = value
    if stage_tools_node is None:
        raise MeasurementError(f"STAGE_TOOLS dict literal not found in {path}")
    return _collect_stage_tools_mapping(stage_tools_node, stage_values)


def _build_session_start_pipeline_block() -> dict[str, Any]:
    """Static sub-fields of the ``pipeline`` object embedded in the full
    session_start response. ``stages``/``stage_tools`` come from
    tapps-core's enum/dict (static config); the rest are literal strings
    inside ``server.py::_build_server_info_data``'s return dict."""
    tree = _parse(_SERVER_PY)
    fn = _find_function(tree, "_build_server_info_data")
    if fn is None:
        raise MeasurementError(f"_build_server_info_data not found in {_SERVER_PY}")
    return_dict = _find_return_dict(fn)
    if return_dict is None:
        raise MeasurementError("_build_server_info_data has no literal return dict")
    pipeline_node = _dict_value_node(return_dict, "pipeline")
    if not isinstance(pipeline_node, ast.Dict):
        raise MeasurementError("_build_server_info_data.pipeline is not a dict literal")

    stages, stage_tools = _parse_pipeline_stage_tools(_PIPELINE_MODELS)
    pipeline: dict[str, Any] = {"stages": stages, "stage_tools": stage_tools}
    for key in ("name", "current_hint", "handoff_file", "runlog_file", "prompts_available"):
        value = _literal_dict_value(pipeline_node, key)
        if value is None:
            raise MeasurementError(f"pipeline.{key} is not a static literal in {_SERVER_PY}")
        pipeline[key] = value
    return pipeline


def _server_info_static_fields() -> dict[str, Any]:
    tree = _parse(_SERVER_PY)
    fn = _find_function(tree, "_build_server_info_data")
    if fn is None:
        raise MeasurementError(f"_build_server_info_data not found in {_SERVER_PY}")
    server_info_dict = _find_return_dict(fn)
    if server_info_dict is None:
        raise MeasurementError("_build_server_info_data has no literal return dict")
    return {
        "quick_start": list(_module_constant(_DEVELOPER_WORKFLOW, "DAILY_STEPS")),
        "critical_rules": _literal_dict_value(server_info_dict, "critical_rules"),
        "checker_environment": _literal_dict_value(server_info_dict, "checker_environment"),
        "checker_environment_note": _literal_dict_value(
            server_info_dict, "checker_environment_note"
        ),
        "pipeline": _build_session_start_pipeline_block(),
        "cli_fallback": _module_constant(_SESSION_START_HELPERS, "CLI_FALLBACK"),
        "mcp_recovery_hint": _module_constant(_SESSION_START_HELPERS, "MCP_RECOVERY_HINT"),
    }


def _build_session_start_static_fields() -> dict[str, Any]:
    fields = _server_info_static_fields()

    core_tree = _parse(_SESSION_START_CORE)
    build_fn = _find_function(core_tree, "build_session_start_data")
    if build_fn is None:
        raise MeasurementError(f"build_session_start_data not found in {_SESSION_START_CORE}")
    session_start_dict = _find_return_dict(build_fn)
    if session_start_dict is None:
        raise MeasurementError("build_session_start_data has no literal return dict")

    for key in ("memory_gc", "memory_consolidation", "memory_doc_validation", "session_capture"):
        value = _literal_dict_value(session_start_dict, key)
        if value is None:
            raise MeasurementError(f"build_session_start_data.{key} is not a static literal")
        fields[key] = value

    missing = [k for k, v in fields.items() if v is None]
    if missing:
        raise MeasurementError(f"session_start static fields not statically resolvable: {missing}")
    return fields


@dataclass
class SessionStartResult:
    static_tokens: int
    static_bytes: int
    fields: dict[str, Any]
    note: str = field(
        default=(
            "Deliberately a conservative floor, not the true per-session payload. "
            "Sums only the unconditional, environment-independent literal content "
            "tapps_session_start(quick=False) embeds (quick_start/critical_rules/"
            "checker_environment_note/pipeline/cli_fallback/mcp_recovery_hint/"
            "memory_* background markers). Excludes dynamic content whose byte "
            "cost is not reproducible from source alone across machines or runs: "
            "installed_checkers, absolute paths, checklist_session_id, timings, "
            "brain_bridge_health, hive_status, call_graph, usage_gaps, "
            "recommended_workflows, diagnostics. A live in-process capture "
            "against this workspace's own source was used to validate scope and "
            "sanity-check magnitude during development (not embedded here: it "
            "dials tapps-brain over localhost:8080, which a verifier may not "
            "have running, and it bakes in this machine's absolute paths), and "
            "is quoted in the script's commit report."
        )
    )


def measure_session_start() -> SessionStartResult:
    fields = _build_session_start_static_fields()
    text = json.dumps(fields)
    byte_count = len(text.encode("utf-8"))
    return SessionStartResult(static_tokens=tokens(text), static_bytes=byte_count, fields=fields)
