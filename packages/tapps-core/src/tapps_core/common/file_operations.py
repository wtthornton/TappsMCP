"""File operation models for Docker-safe content-return pattern.

When TappsMCP runs inside a Docker container with a read-only workspace mount,
tools cannot write files directly.  Instead they return a ``FileManifest``
containing the file contents and agent instructions so the AI client (Claude
Code, Cursor, etc.) can apply the writes using its own native capabilities.

See Epic 87 for the full design: docs/planning/epics/EPIC-87-*.md
"""

from __future__ import annotations

import os
import tempfile
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Write-mode detection
# ---------------------------------------------------------------------------


class WriteMode(Enum):
    """Whether the tool should write files directly or return content."""

    DIRECT_WRITE = "direct_write"
    CONTENT_RETURN = "content_return"


def detect_write_mode(project_root: Path) -> WriteMode:
    """Detect whether we can write to *project_root*.

    Resolution order:

    1. ``TAPPS_WRITE_MODE`` env var (``"direct"`` or ``"content"``) — explicit
       override, always wins.
    2. Filesystem probe — attempt to create+delete a temp file in
       *project_root*.  If the probe fails (``OSError``), assume read-only and
       return ``CONTENT_RETURN``.
    """
    explicit = os.environ.get("TAPPS_WRITE_MODE", "").lower().strip()
    if explicit == "direct":
        return WriteMode.DIRECT_WRITE
    if explicit == "content":
        return WriteMode.CONTENT_RETURN

    # Filesystem write probe
    try:
        with tempfile.NamedTemporaryFile(
            dir=project_root,
            prefix=".tapps-write-test-",
            delete=True,
        ):
            pass  # created + deleted successfully
        return WriteMode.DIRECT_WRITE
    except OSError:
        return WriteMode.CONTENT_RETURN


# ---------------------------------------------------------------------------
# FileOperation models
# ---------------------------------------------------------------------------


class FileOperation(BaseModel):
    """A single file to be written by the AI client.

    The ``content`` field contains the *exact* bytes (as a UTF-8 string) that
    should be written.  The agent must not modify, reformat, or "improve" the
    content — it should be written verbatim.
    """

    path: str = Field(
        description=(
            "Relative path from project root, using forward slashes.  "
            "Example: '.claude/hooks/tapps-pre-edit.sh'"
        ),
    )
    content: str = Field(
        description="Full file content to write.  Write verbatim — do not modify.",
    )
    mode: str = Field(
        description=(
            "Write mode: 'create' = new file only (error if exists), "
            "'overwrite' = replace entirely, "
            "'merge' = smart-merge with existing content (see agent_instructions)."
        ),
    )
    encoding: str = Field(
        default="utf-8",
        description="File encoding.",
    )
    description: str = Field(
        default="",
        description="Human-readable explanation of what this file does and why.",
    )
    priority: int = Field(
        default=10,
        description=(
            "Write order — lower numbers are written first.  "
            "Config files should be 1-3, content files 5-10, hooks 10+."
        ),
    )


class AgentInstructions(BaseModel):
    """Guidance for the AI agent that will apply the file operations.

    Every field is designed to help LLMs reliably apply file writes without
    user intervention.  See Epic 87 research notes for why each field exists.
    """

    persona: str = Field(
        default=(
            "You are a project scaffolding assistant applying TappsMCP "
            "configuration files.  Write each file exactly as provided — "
            "do not modify content, add comments, or reformat."
        ),
        description="Role the agent should adopt when applying these files.",
    )
    tool_preference: str = Field(
        default=(
            "Use the Write tool for files with mode 'create' or 'overwrite'.  "
            "For files with mode 'merge', read the existing file first, then "
            "use the Edit tool to replace only the managed sections."
        ),
        description="Which tool to use for writing (Write for new, Edit for merges).",
    )
    verification_steps: list[str] = Field(
        default_factory=lambda: [
            "After writing all files, run 'git status' to show the user what changed.",
            "Verify that key files exist (AGENTS.md, .tapps-mcp.yaml if expected).",
        ],
        description="Steps to verify after all files are written.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Important caveats the agent should communicate to the user.",
    )


class FileManifest(BaseModel):
    """Complete manifest of file operations returned by a tool in content-return mode.

    This is the top-level structured output that tools return when they cannot
    (or should not) write files directly.  The AI client reads the manifest and
    applies the file operations using its own native write capabilities.
    """

    mode: str = Field(
        default="content_return",
        description="Always 'content_return' when this manifest is present.",
    )
    reason: str = Field(
        default="Docker container detected — returning file contents for client-side application.",
        description="Why content-return mode was used (shown to user).",
    )
    files: list[FileOperation] = Field(
        default_factory=list,
        description="Ordered list of file operations to apply.",
    )
    agent_instructions: AgentInstructions = Field(
        default_factory=AgentInstructions,
        description="Guidance for the AI agent applying these files.",
    )
    summary: str = Field(
        default="",
        description="One-line summary for the agent to relay to the user.",
    )
    source_version: str = Field(
        default="",
        description="TappsMCP/DocsMCP version that generated these files.",
    )
    backup_recommended: bool = Field(
        default=True,
        description="Whether the agent should recommend backing up before applying.",
    )

    def sorted_files(self) -> list[FileOperation]:
        """Return files sorted by priority (lowest first)."""
        return sorted(self.files, key=lambda f: f.priority)

    def to_text_content(self) -> str:
        """Serialize to a human-readable text block for MCP ``content``.

        This provides backward compatibility for clients that do not support
        ``structuredContent``.
        """
        lines: list[str] = []
        lines.append(f"## {self.summary or 'File Operations'}")
        lines.append("")
        lines.append(f"**Mode:** {self.mode}")
        lines.append(f"**Reason:** {self.reason}")
        if self.source_version:
            lines.append(f"**Version:** {self.source_version}")
        lines.append(f"**Files:** {len(self.files)}")
        lines.append("")

        # Agent instructions
        instr = self.agent_instructions
        lines.append("### Agent Instructions")
        lines.append("")
        lines.append(f"**Persona:** {instr.persona}")
        lines.append(f"**Tool Preference:** {instr.tool_preference}")
        if instr.verification_steps:
            lines.append("**Verification Steps:**")
            for step in instr.verification_steps:
                lines.append(f"  - {step}")
        if instr.warnings:
            lines.append("**Warnings:**")
            for w in instr.warnings:
                lines.append(f"  - {w}")
        lines.append("")

        # File listing
        lines.append("### Files to Write")
        lines.append("")
        for f in self.sorted_files():
            lines.append(f"#### [{f.priority}] `{f.path}` ({f.mode})")
            if f.description:
                lines.append(f.description)
            lines.append("```")
            lines.append(f.content)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def to_structured_content(self) -> dict[str, Any]:
        """Serialize for MCP ``structuredContent`` response field."""
        return self.model_dump(mode="json")

    def to_response_data(self) -> dict[str, Any]:
        """Serialize for embedding in the existing ToolResponse ``data`` dict.

        This keeps backward compatibility with the ``success_response()``
        helper while adding the manifest as a nested key.
        """
        data: dict[str, Any] = {
            "mode": self.mode,
            "reason": self.reason,
            "summary": self.summary,
            "source_version": self.source_version,
            "backup_recommended": self.backup_recommended,
            "file_count": len(self.files),
            "files": [
                {
                    "path": f.path,
                    "mode": f.mode,
                    "description": f.description,
                    "priority": f.priority,
                    "content_length": len(f.content),
                }
                for f in self.sorted_files()
            ],
            "agent_instructions": self.agent_instructions.model_dump(mode="json"),
        }
        return data

    def to_full_response_data(self) -> dict[str, Any]:
        """Like ``to_response_data()`` but includes full file contents.

        Use this when the response is the primary delivery mechanism (Docker
        mode).  For local mode, ``to_response_data()`` omits content to keep
        responses small.
        """
        data = self.to_response_data()
        data["files"] = [f.model_dump(mode="json") for f in self.sorted_files()]
        return data
