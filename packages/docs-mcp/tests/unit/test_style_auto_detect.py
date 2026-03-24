"""Integration tests for style_auto_detect_terms (Epic 84.3)."""

from __future__ import annotations

from pathlib import Path

import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_docs_check_style_uses_auto_detected_leverage_segment(tmp_path: Path) -> None:
    """CamelCase class yields 'Leverage' token so default jargon 'leverage' is skipped."""
    from unittest.mock import patch

    from docs_mcp.server_val_tools import docs_check_style

    _write(
        tmp_path / "src" / "models.py",
        "class LeverageCore:\n    pass\n",
    )
    _write(
        tmp_path / "README.md",
        "# Project\n\nWe leverage this design.\n",
    )

    from docs_mcp.config.settings import DocsMCPSettings

    settings = DocsMCPSettings(
        project_root=tmp_path,
        style_auto_detect_terms=True,
        style_enabled_rules=["jargon"],
        style_custom_terms=[],
    )

    with patch("docs_mcp.server_val_tools._get_settings", return_value=settings):
        result = await docs_check_style(project_root=str(tmp_path))

    assert result["success"] is True
    assert result["data"]["total_issues"] == 0
