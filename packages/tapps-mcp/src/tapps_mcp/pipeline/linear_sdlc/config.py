"""Configuration dataclass for Linear SDLC template rendering (TAP-410)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinearSDLCConfig:
    """Parameters that drive Linear SDLC template rendering.

    Attributes:
        issue_prefix: Linear issue prefix, e.g. ``"TAP"``. Used in branch names
            (``tap-123-...``), grep patterns in hooks, and example text in
            workflow docs.
        agent_name: Canonical agent identifier shown in issue-comment
            templates, e.g. ``"claude-sonnet-4-6"``.
        skill_path: Filesystem path (as rendered text) where the Linear
            Claude skill is installed. Used by hook command lines.
        team_id: Optional Linear team identifier (e.g. ``"TAP"``). Reserved
            for downstream rendering that needs to target a specific team.
        project_id: Optional Linear project slug or UUID. Reserved for
            tapps_init to bake into generated ``CLAUDE.local.md`` policies.
    """

    issue_prefix: str = "TAP"
    agent_name: str = "claude-sonnet-4-6"
    skill_path: str = "~/.claude/skills/linear"
    team_id: str = ""
    project_id: str = ""

    @property
    def prefix_lower(self) -> str:
        """Lowercased issue prefix used in git branch names."""
        return self.issue_prefix.lower()

    def __post_init__(self) -> None:
        if not self.issue_prefix:
            msg = "LinearSDLCConfig.issue_prefix must be non-empty"
            raise ValueError(msg)
        if not self.issue_prefix.isupper():
            msg = f"issue_prefix must be uppercase (got {self.issue_prefix!r})"
            raise ValueError(msg)
