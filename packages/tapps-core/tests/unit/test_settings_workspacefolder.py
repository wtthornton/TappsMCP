"""TAP-2199 regression — TappsMCPSettings.project_root must never accept an
unresolved VS Code variable reference like ``${workspaceFolder}``.

When Claude Code CLI launches the server with ``TAPPS_MCP_PROJECT_ROOT`` set
to the literal ``${workspaceFolder}`` (because the host did not expand the
variable), the path validator silently mkdirs a phantom directory at the
real project root and the upgrade flow plans against the wrong path. The
field validator added in tapps-core fails fast instead so the broken value
can never reach :mod:`pathlib.Path.mkdir`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


class TestProjectRootRejectsUnresolvedVariables:
    """Layer-B defense-in-depth for TAP-2199."""

    def test_workspacefolder_literal_rejected(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        with pytest.raises(ValidationError) as exc_info:
            TappsMCPSettings(project_root="${workspaceFolder}")  # type: ignore[arg-type]
        assert "TAP-2199" in str(exc_info.value)

    def test_other_unresolved_variable_rejected(self) -> None:
        """Any unresolved ``${...}`` ref is rejected, not just workspaceFolder."""
        from tapps_core.config.settings import TappsMCPSettings

        with pytest.raises(ValidationError):
            TappsMCPSettings(project_root="${foo}/projects")  # type: ignore[arg-type]

    def test_workspacefolder_via_env_rejected(self, monkeypatch, tmp_path: Path) -> None:
        """Same guard fires when the value arrives via TAPPS_MCP_PROJECT_ROOT env."""
        from tapps_core.config.settings import TappsMCPSettings

        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", "${workspaceFolder}")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValidationError) as exc_info:
            TappsMCPSettings()
        assert "TAP-2199" in str(exc_info.value)

    def test_absolute_path_accepted(self, tmp_path: Path) -> None:
        """A real absolute path goes through unchanged."""
        from tapps_core.config.settings import TappsMCPSettings

        settings = TappsMCPSettings(project_root=tmp_path)
        assert settings.project_root == tmp_path

    def test_relative_dot_accepted(self) -> None:
        """``.`` (the Claude Code CWD convention) remains valid."""
        from tapps_core.config.settings import TappsMCPSettings

        settings = TappsMCPSettings(project_root=".")  # type: ignore[arg-type]
        assert str(settings.project_root) == "."

    def test_error_message_points_at_remediation(self) -> None:
        """The ValueError text must tell the user how to fix the broken env."""
        from tapps_core.config.settings import TappsMCPSettings

        with pytest.raises(ValidationError) as exc_info:
            TappsMCPSettings(project_root="${workspaceFolder}")  # type: ignore[arg-type]
        message = str(exc_info.value)
        assert "tapps-mcp upgrade" in message
