"""Document-consumer smoke tests for validate_changed + judge integration (TAP-3688-3691)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tapps_core.config.settings import TappsMCPSettings, ValidateChangedSettings


@pytest.mark.integration
class TestDocumentConsumerValidateChangedSmoke:
    @pytest.mark.asyncio
    async def test_zero_scorable_files_runs_configured_judges(self, tmp_path) -> None:
        """YAML-only git diff should still execute blocking judges via validate_changed."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        root = tmp_path / "consumer"
        root.mkdir()
        (root / "reports").mkdir()
        (root / ".git").mkdir()
        build = root / "build-pdfs.mjs"
        build.write_text('spawn("node", ["build.mjs", "--audit"]);\n')

        judges = [
            {
                "type": "grep",
                "target": "build-pdfs.mjs",
                "expect": r"--audit",
                "description": "build script includes audit flag",
                "blocking": True,
                "when_changed": ["brands/**"],
            }
        ]
        settings = TappsMCPSettings(
            project_root=root,
            validate_changed=ValidateChangedSettings(judges=judges),
        )

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings", return_value=settings),
            patch(
                "tapps_mcp.tools.validate_changed_collection._discover_changed_files",
                return_value=[],
            ),
            patch(
                "tapps_core.metrics.judge._git_changed_paths",
                return_value=["brands/acme.yaml"],
            ),
        ):
            result = await tapps_validate_changed(file_paths="")

        data = result["data"]
        assert data["files_validated"] == 0
        assert data["all_gates_passed"] is True
        assert data.get("judges_passed") is True
        assert any(r.get("result") == "pass" for r in data.get("judge_results", []))

    @pytest.mark.asyncio
    async def test_blocking_judge_failure_sets_all_gates_passed_false(self, tmp_path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        root = tmp_path / "consumer_fail"
        root.mkdir()
        (root / "reports").mkdir()
        (root / ".git").mkdir()
        build = root / "build-pdfs.mjs"
        build.write_text("// --audit comment only\n")

        judges = [
            {
                "type": "grep",
                "target": "build-pdfs.mjs",
                "expect": r"--audit",
                "blocking": True,
                "when_changed": ["brands/**"],
            }
        ]
        settings = TappsMCPSettings(
            project_root=root,
            validate_changed=ValidateChangedSettings(judges=judges),
        )

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings", return_value=settings),
            patch(
                "tapps_mcp.tools.validate_changed_collection._discover_changed_files",
                return_value=[],
            ),
            patch(
                "tapps_core.metrics.judge._git_changed_paths",
                return_value=["brands/acme.yaml"],
            ),
        ):
            result = await tapps_validate_changed(file_paths="")

        data = result["data"]
        assert data["all_gates_passed"] is False
        assert data.get("judges_passed") is False
        assert any(r.get("result") == "fail" for r in data.get("judge_results", []))
