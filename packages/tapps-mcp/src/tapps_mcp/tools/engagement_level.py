"""Helpers for the ``tapps_set_engagement_level`` tool handler.

Extracted from ``server_pipeline_tools.py`` to reduce its size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_engagement_yaml(config_path: Path) -> dict[str, Any] | str:
    """Load existing .tapps-mcp.yaml; returns dict on success, error string on failure."""
    import yaml

    if not config_path.exists():
        return {}
    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return f"Could not read existing .tapps-mcp.yaml: {e}"
    if not isinstance(data, dict):
        return {}
    return data


def write_engagement_yaml(config_path: Path, yaml_content: str) -> str | None:
    """Write YAML to disk; returns error string on failure, else None."""
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            f.write(yaml_content)
    except OSError as e:
        return f"Could not write .tapps-mcp.yaml: {e}"
    return None


def engagement_manifest(yaml_content: str, level: str, settings: Any) -> dict[str, Any]:
    """Build the content-return manifest for engagement level change."""
    from tapps_core.common.file_operations import (
        AgentInstructions,
        FileManifest,
        FileOperation,
    )

    manifest = FileManifest(
        summary=f"Set engagement level to {level}",
        source_version=settings.version if hasattr(settings, "version") else "",
        files=[
            FileOperation(
                path=".tapps-mcp.yaml",
                content=yaml_content,
                mode="overwrite",
                description="TappsMCP config with updated engagement level.",
                priority=1,
            ),
        ],
        agent_instructions=AgentInstructions(
            persona=(
                "You are a configuration assistant. Write the config file exactly as provided."
            ),
            tool_preference="Use the Write tool to overwrite .tapps-mcp.yaml.",
            verification_steps=[
                "Verify .tapps-mcp.yaml contains the expected engagement level.",
            ],
            warnings=[
                "Config changes affect all subsequent tool behavior.",
            ],
        ),
    )
    return manifest.to_full_response_data()


__all__ = [
    "engagement_manifest",
    "read_engagement_yaml",
    "write_engagement_yaml",
]
