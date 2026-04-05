"""Business expert management tool handlers for TappsMCP.

Provides the tapps_manage_experts MCP tool with actions:
list, add, remove, scaffold, validate.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from tapps_mcp.server_helpers import error_response, success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from mcp.types import ToolAnnotations

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_VALID_ACTIONS = {"list", "add", "remove", "scaffold", "validate", "auto_generate"}

_ANNOTATIONS_EXPERTS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_experts_yaml_path(project_root: Path) -> Path:
    """Return the path to .tapps-mcp/experts.yaml."""
    return project_root / ".tapps-mcp" / "experts.yaml"


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write YAML atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent), suffix=".yaml.tmp",
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _load_yaml(yaml_path: Path) -> dict[str, Any]:
    """Load and return parsed YAML data, or empty experts dict if file absent."""
    if not yaml_path.exists():
        return {"experts": []}
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if raw is None:
        return {"experts": []}
    if not isinstance(raw, dict):
        msg = f"Expected a mapping in {yaml_path}, got {type(raw).__name__}"
        raise ValueError(msg)
    if "experts" not in raw:
        raw["experts"] = []
    return raw


def _record_call(tool_name: str) -> None:
    """Record a tool call in the session checklist tracker."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.record(tool_name)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _handle_list(project_root: Path) -> dict[str, Any]:
    """List configured business experts with knowledge status."""
    from tapps_core.experts.business_config import load_business_experts
    from tapps_core.experts.business_knowledge import (
        get_business_knowledge_path,
    )

    experts = load_business_experts(project_root)
    expert_list: list[dict[str, Any]] = []
    for expert in experts:
        knowledge_path = get_business_knowledge_path(project_root, expert)
        md_files = list(knowledge_path.glob("*.md")) if knowledge_path.exists() else []
        expert_list.append({
            "expert_id": expert.expert_id,
            "expert_name": expert.expert_name,
            "primary_domain": expert.primary_domain,
            "description": expert.description,
            "keywords": expert.keywords,
            "rag_enabled": expert.rag_enabled,
            "knowledge_dir": expert.knowledge_dir,
            "knowledge_path": str(knowledge_path),
            "knowledge_exists": knowledge_path.exists(),
            "knowledge_file_count": len(md_files),
        })

    return {
        "action": "list",
        "experts": expert_list,
        "count": len(expert_list),
    }


def _validate_add_params(
    expert_id: str,
    expert_name: str,
    primary_domain: str,
    existing_ids: set[str],
) -> dict[str, Any] | None:
    """Validate add-action parameters. Returns error dict or None if valid."""
    if not expert_id:
        return {"error": "missing_expert_id", "message": "expert_id is required for add."}
    if not expert_name:
        return {"error": "missing_expert_name", "message": "expert_name is required for add."}
    if not primary_domain:
        return {"error": "missing_primary_domain", "message": "primary_domain is required for add."}
    if not expert_id.startswith("expert-"):
        return {
            "error": "invalid_expert_id",
            "message": f"expert_id must start with 'expert-', got: {expert_id!r}",
        }

    from tapps_core.experts.registry import ExpertRegistry

    builtin_ids = {e.expert_id for e in ExpertRegistry.BUILTIN_EXPERTS}
    if expert_id in builtin_ids:
        return {
            "error": "builtin_collision",
            "message": (
                f"expert_id '{expert_id}' collides with a built-in expert. "
                f"Choose a different ID."
            ),
        }
    if expert_id in existing_ids:
        return {
            "error": "duplicate_expert_id",
            "message": f"expert_id '{expert_id}' already exists in experts.yaml.",
        }
    return None


def _handle_add(
    project_root: Path,
    expert_id: str,
    expert_name: str,
    primary_domain: str,
    description: str,
    keywords: list[str],
    rag_enabled: bool,
    knowledge_dir: str,
) -> dict[str, Any]:
    """Add a new business expert to experts.yaml."""
    yaml_path = _get_experts_yaml_path(project_root)
    data = _load_yaml(yaml_path)
    existing_ids = {e["expert_id"] for e in data["experts"] if isinstance(e, dict)}

    validation_error = _validate_add_params(
        expert_id, expert_name, primary_domain, existing_ids,
    )
    if validation_error is not None:
        return validation_error

    entry: dict[str, Any] = {
        "expert_id": expert_id,
        "expert_name": expert_name,
        "primary_domain": primary_domain,
    }
    if description:
        entry["description"] = description
    if keywords:
        entry["keywords"] = keywords
    if not rag_enabled:
        entry["rag_enabled"] = rag_enabled
    if knowledge_dir:
        entry["knowledge_dir"] = knowledge_dir

    data["experts"].append(entry)

    # Epic 87: content-return mode for Docker/read-only
    from tapps_core.common.file_operations import WriteMode, detect_write_mode

    write_mode = detect_write_mode(project_root)

    if write_mode == WriteMode.DIRECT_WRITE:
        _atomic_write_yaml(yaml_path, data)

    logger.info(
        "business_expert.added",
        expert_id=expert_id,
        yaml_path=str(yaml_path),
    )

    # Optionally scaffold knowledge directory
    scaffolded_path: str | None = None
    if (knowledge_dir or primary_domain) and write_mode == WriteMode.DIRECT_WRITE:
        from tapps_core.experts.business_knowledge import scaffold_knowledge_directory
        from tapps_core.experts.models import ExpertConfig

        config = ExpertConfig(
            expert_id=expert_id,
            expert_name=expert_name,
            primary_domain=primary_domain,
            description=description,
            keywords=keywords,
            rag_enabled=rag_enabled,
            knowledge_dir=knowledge_dir or None,
            is_builtin=False,
        )
        scaffolded = scaffold_knowledge_directory(project_root, config)
        scaffolded_path = str(scaffolded)

    result: dict[str, Any] = {
        "action": "add",
        "expert_id": expert_id,
        "yaml_path": str(yaml_path),
        "scaffolded_path": scaffolded_path,
    }

    if write_mode == WriteMode.CONTENT_RETURN:
        import yaml as _yaml

        from tapps_core.common.file_operations import (
            AgentInstructions,
            FileManifest,
            FileOperation,
        )

        yaml_content = _yaml.dump(data, default_flow_style=False, sort_keys=False)
        manifest = FileManifest(
            summary=f"Add business expert: {expert_id}",
            files=[
                FileOperation(
                    path=".tapps-mcp/experts.yaml",
                    content=yaml_content,
                    mode="overwrite",
                    description="Business experts config with new expert entry.",
                    priority=1,
                ),
            ],
            agent_instructions=AgentInstructions(
                persona="You are a configuration assistant. Write the config file exactly.",
                tool_preference="Use the Write tool to overwrite .tapps-mcp/experts.yaml.",
                verification_steps=["Verify .tapps-mcp/experts.yaml contains the new expert."],
                warnings=["Config changes affect expert consultation behavior."],
            ),
        )
        result["content_return"] = True
        result["file_manifest"] = manifest.to_full_response_data()

    return result


def _handle_remove(project_root: Path, expert_id: str) -> dict[str, Any]:
    """Remove a business expert from experts.yaml."""
    if not expert_id:
        return {"error": "missing_expert_id", "message": "expert_id is required for remove."}

    yaml_path = _get_experts_yaml_path(project_root)
    if not yaml_path.exists():
        return {
            "error": "not_found",
            "message": f"experts.yaml not found at {yaml_path}.",
        }

    data = _load_yaml(yaml_path)
    original_count = len(data["experts"])
    data["experts"] = [
        e for e in data["experts"]
        if not (isinstance(e, dict) and e.get("expert_id") == expert_id)
    ]

    if len(data["experts"]) == original_count:
        return {
            "error": "not_found",
            "message": f"expert_id '{expert_id}' not found in experts.yaml.",
        }

    _atomic_write_yaml(yaml_path, data)

    logger.info(
        "business_expert.removed",
        expert_id=expert_id,
        yaml_path=str(yaml_path),
    )

    return {
        "action": "remove",
        "expert_id": expert_id,
        "remaining_count": len(data["experts"]),
    }


def _handle_scaffold(project_root: Path, expert_id: str) -> dict[str, Any]:
    """Scaffold knowledge directory for a business expert."""
    if not expert_id:
        return {"error": "missing_expert_id", "message": "expert_id is required for scaffold."}

    from tapps_core.experts.business_config import load_business_experts
    from tapps_core.experts.business_knowledge import scaffold_knowledge_directory

    experts = load_business_experts(project_root)
    target = None
    for expert in experts:
        if expert.expert_id == expert_id:
            target = expert
            break

    if target is None:
        return {
            "error": "not_found",
            "message": f"expert_id '{expert_id}' not found in experts.yaml.",
        }

    # Epic 87: content-return mode for Docker/read-only
    from tapps_core.common.file_operations import WriteMode, detect_write_mode

    write_mode = detect_write_mode(project_root)

    if write_mode == WriteMode.DIRECT_WRITE:
        knowledge_path = scaffold_knowledge_directory(project_root, target)
        return {
            "action": "scaffold",
            "expert_id": expert_id,
            "knowledge_path": str(knowledge_path),
        }

    # Content-return: generate knowledge file templates as FileOps
    from tapps_core.common.file_operations import (
        AgentInstructions,
        FileManifest,
        FileOperation,
    )

    kdir = target.knowledge_dir or target.primary_domain
    base = f".tapps-mcp/experts/knowledge/{kdir}"
    manifest = FileManifest(
        summary=f"Scaffold knowledge directory for expert: {expert_id}",
        files=[
            FileOperation(
                path=f"{base}/README.md",
                content=f"# {target.expert_name}\n\n{target.description or ''}\n",
                mode="create",
                description=f"Knowledge directory README for {expert_id}.",
                priority=5,
            ),
            FileOperation(
                path=f"{base}/overview.md",
                content=(
                    f"# {target.primary_domain} Overview\n\n"
                    "Add domain-specific knowledge here.\n"
                ),
                mode="create",
                description=f"Domain overview for {expert_id}.",
                priority=5,
            ),
        ],
        agent_instructions=AgentInstructions(
            persona="You are a knowledge scaffolding assistant. Create the files as provided.",
            tool_preference="Use the Write tool. Create parent directories as needed.",
            verification_steps=[f"Verify {base}/ directory structure was created."],
            warnings=[],
        ),
    )
    return {
        "action": "scaffold",
        "expert_id": expert_id,
        "content_return": True,
        "file_manifest": manifest.to_full_response_data(),
    }


def _handle_validate(project_root: Path) -> dict[str, Any]:
    """Validate knowledge directories for all business experts."""
    from tapps_core.experts.business_config import load_business_experts
    from tapps_core.experts.business_knowledge import validate_business_knowledge

    experts = load_business_experts(project_root)
    result = validate_business_knowledge(project_root, experts)

    return {
        "action": "validate",
        "valid": result.valid,
        "missing": result.missing,
        "empty": result.empty,
        "warnings": result.warnings,
        "expert_count": len(experts),
    }


def _handle_auto_generate(
    project_root: Path,
    dry_run: bool,
    max_experts: int,
    include_knowledge: bool,
) -> dict[str, Any]:
    """Auto-generate business experts from codebase analysis."""
    from tapps_core.experts.auto_generator import auto_generate_experts
    from tapps_mcp.project.profiler import detect_project_profile

    profile = detect_project_profile(project_root)
    result = auto_generate_experts(
        project_root=project_root,
        libraries=profile.tech_stack.libraries,
        frameworks=profile.tech_stack.frameworks,
        domains=profile.tech_stack.domains,
        max_experts=max_experts,
        dry_run=dry_run,
        include_knowledge=include_knowledge,
    )

    return {
        "action": "auto_generate",
        "dry_run": dry_run,
        "suggestions": [
            {
                "domain": s.domain,
                "expert_name": s.expert_name,
                "description": s.description,
                "keywords": s.keywords,
                "confidence": round(s.confidence, 2),
                "rationale": s.rationale,
                "detected_libraries": s.detected_libraries,
            }
            for s in result.suggestions
        ],
        "generated": result.generated,
        "scaffolded": result.scaffolded,
        "skipped_builtin_count": len(result.skipped_builtin),
        "skipped_existing_count": len(result.skipped_existing),
        "suggestion_count": len(result.suggestions),
        "generated_count": len(result.generated),
    }


# ---------------------------------------------------------------------------
# Public MCP tool
# ---------------------------------------------------------------------------


async def tapps_manage_experts(
    action: str,
    expert_id: str = "",
    expert_name: str = "",
    primary_domain: str = "",
    description: str = "",
    keywords: str = "",
    rag_enabled: bool = True,
    knowledge_dir: str = "",
    dry_run: bool = True,
    max_experts: int = 5,
    include_knowledge: bool = True,
) -> dict[str, Any]:
    """Manage user-defined business experts (CRUD + validation + auto-generation).

    Args:
        action: One of "list", "add", "remove", "scaffold", "validate", "auto_generate".
        expert_id: Expert identifier (required for add/remove/scaffold).
            Must start with "expert-".
        expert_name: Human-readable name (required for add).
        primary_domain: Primary domain of authority (required for add).
        description: Short description of the expert's focus (optional).
        keywords: Comma-separated keywords for domain detection (optional).
        rag_enabled: Whether RAG retrieval is enabled (default: True).
        knowledge_dir: Override knowledge directory name (optional).
        dry_run: For auto_generate: preview suggestions without writing (default: True).
        max_experts: For auto_generate: max experts to generate (default: 5).
        include_knowledge: For auto_generate: scaffold knowledge dirs (default: True).

    Actions:
        list: List all configured business experts with knowledge status.
        add: Add a new business expert (creates experts.yaml if needed,
            scaffolds knowledge directory).
        remove: Remove a business expert from experts.yaml.
        scaffold: Create knowledge directory with README template.
        validate: Validate knowledge directories for all experts.
        auto_generate: Analyze codebase and suggest/create experts for uncovered domains.
    """
    _record_call("tapps_manage_experts")

    t0 = time.perf_counter()

    if action not in _VALID_ACTIONS:
        return error_response(
            "tapps_manage_experts",
            "invalid_action",
            f"Invalid action '{action}'. "
            f"Must be one of: {', '.join(sorted(_VALID_ACTIONS))}",
        )

    from tapps_core.config.settings import load_settings

    settings = load_settings()
    project_root = settings.project_root

    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

    try:
        if action == "list":
            result_data = _handle_list(project_root)
        elif action == "add":
            result_data = _handle_add(
                project_root,
                expert_id=expert_id,
                expert_name=expert_name,
                primary_domain=primary_domain,
                description=description,
                keywords=keyword_list,
                rag_enabled=rag_enabled,
                knowledge_dir=knowledge_dir,
            )
        elif action == "remove":
            result_data = _handle_remove(project_root, expert_id=expert_id)
        elif action == "scaffold":
            result_data = _handle_scaffold(project_root, expert_id=expert_id)
        elif action == "auto_generate":
            result_data = _handle_auto_generate(
                project_root,
                dry_run=dry_run,
                max_experts=max_experts,
                include_knowledge=include_knowledge,
            )
        else:  # validate
            result_data = _handle_validate(project_root)
    except Exception as exc:
        return error_response(
            "tapps_manage_experts",
            "action_failed",
            f"Expert {action} failed: {exc}",
        )

    # If the handler returned an error dict, wrap it
    if "error" in result_data:
        return error_response(
            "tapps_manage_experts",
            result_data["error"],
            result_data.get("message", "Unknown error"),
        )

    elapsed = int((time.perf_counter() - t0) * 1000)
    return success_response("tapps_manage_experts", elapsed, result_data)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register expert management tools on the shared *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_manage_experts" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_EXPERTS)(tapps_manage_experts)
