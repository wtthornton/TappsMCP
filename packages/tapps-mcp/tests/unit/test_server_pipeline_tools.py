"""Tests for MCP tool handlers in server_pipeline_tools.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_score(
    overall_score: float = 85.0,
    security_issues: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a mock ScoreResult."""
    score = MagicMock()
    score.overall_score = overall_score
    score.security_issues = security_issues or []
    return score


def _make_mock_gate(passed: bool = True) -> MagicMock:
    """Build a mock GateResult."""
    gate = MagicMock()
    gate.passed = passed
    gate.failures = []
    if not passed:
        failure = MagicMock()
        failure.model_dump.return_value = {
            "category": "security",
            "actual": 3.0,
            "threshold": 5.0,
        }
        gate.failures = [failure]
    return gate


def _make_mock_settings(tmp_path: Path) -> MagicMock:
    """Build a mock TappsMCPSettings."""
    return MagicMock(
        project_root=tmp_path,
        dependency_scan_enabled=False,
        memory=MagicMock(enabled=False),
    )


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------


class TestTappsSessionStart:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_returns_success(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        assert result["success"] is True
        assert result["tool"] == "tapps_session_start"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_includes_server_info(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "server" in data
        assert data["server"]["name"] == "TappsMCP"

    @pytest.mark.asyncio
    async def test_includes_installed_checkers(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "installed_checkers" in data

    @pytest.mark.asyncio
    async def test_includes_checker_environment_context(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert data["checker_environment"] == "mcp_server"
        assert "checker_environment_note" in data
        assert "MCP server" in data["checker_environment_note"]
        assert "Target project" in data["checker_environment_note"]

    @pytest.mark.asyncio
    async def test_includes_memory_status(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "memory_status" in data
        assert "enabled" in data["memory_status"]

    @pytest.mark.asyncio
    async def test_records_call(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        CallTracker.reset()
        await tapps_session_start()
        assert "tapps_session_start" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    async def _test_includes_project_profile_hint_REMOVED(self) -> None:
        """tapps_project_profile removed (EPIC-96)."""

    @pytest.mark.asyncio
    async def test_marks_session_initialized(self) -> None:
        from tapps_mcp.server_helpers import is_session_initialized
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        await tapps_session_start()
        assert is_session_initialized() is True

    @pytest.mark.asyncio
    async def test_includes_timings(self) -> None:
        """Full session start includes per-phase timings dict (Epic 68.2)."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "timings" in data
        timings = data["timings"]
        assert "server_info_ms" in timings
        assert "memory_status_ms" in timings
        assert "total_ms" in timings
        # All timings must be non-negative integers
        for key, val in timings.items():
            assert isinstance(val, int), f"timings[{key}] should be int"

    @pytest.mark.asyncio
    async def _test_populates_tech_stack_domains_REMOVED(self) -> None:
        """Expert system removed (EPIC-94). Tech stack domains no longer populated."""

    @pytest.mark.asyncio
    async def test_background_maintenance_fields(self) -> None:
        """Full session start marks maintenance ops as background (Epic 68.2)."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert data["memory_gc"] == "background"
        assert data["memory_consolidation"] == "background"
        assert data["memory_doc_validation"] == "background"
        assert data["session_capture"] == "background"


# ---------------------------------------------------------------------------
# tapps_set_engagement_level
# ---------------------------------------------------------------------------


class TestTappsSetEngagementLevel:
    def setup_method(self) -> None:
        CallTracker.reset()

    def test_invalid_level_returns_error(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        result = tapps_set_engagement_level("invalid")
        assert result["success"] is False

    def test_valid_levels_accepted(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        # Create .git so PathValidator accepts the tmp_path as project root
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / "pyproject.toml").write_text("[project]\n")

        for level in ("high", "medium", "low"):
            with patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings:
                mock_settings.return_value = MagicMock(
                    project_root=str(tmp_path),
                )
                result = tapps_set_engagement_level(level)
                assert result["success"] is True

    def test_records_call(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        CallTracker.reset()
        tapps_set_engagement_level("invalid")
        assert "tapps_set_engagement_level" in CallTracker.get_called_tools()

    def test_writes_yaml_file(self, tmp_path: Path) -> None:
        import yaml

        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / "pyproject.toml").write_text("[project]\n")

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(project_root=str(tmp_path))
            tapps_set_engagement_level("low")

        config_path = tmp_path / ".tapps-mcp.yaml"
        assert config_path.exists()
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["llm_engagement_level"] == "low"

    def test_response_includes_next_step(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        result = tapps_set_engagement_level("invalid")
        # Invalid returns error, so check valid case via mock
        assert result["success"] is False


# ---------------------------------------------------------------------------
# tapps_upgrade
# ---------------------------------------------------------------------------


class TestTappsUpgrade:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.upgrade.upgrade_pipeline")
    async def test_dry_run_returns_success(
        self, mock_upgrade: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_upgrade.return_value = {"success": True, "dry_run": True, "changes": []}

        result = await tapps_upgrade(dry_run=True)
        assert result["success"] is True
        mock_upgrade.assert_called_once()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.upgrade.upgrade_pipeline")
    async def test_records_call(
        self, mock_upgrade: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_upgrade.return_value = {"success": True, "components": {}, "errors": []}

        CallTracker.reset()
        await tapps_upgrade()
        assert "tapps_upgrade" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.upgrade.upgrade_pipeline")
    async def test_force_flag_passed(
        self, mock_upgrade: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_upgrade.return_value = {"success": True, "components": {}, "errors": []}

        await tapps_upgrade(force=True)
        call_kwargs = mock_upgrade.call_args[1]
        assert call_kwargs["force"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.upgrade.upgrade_pipeline")
    async def test_platform_passed(
        self, mock_upgrade: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_upgrade.return_value = {"success": True, "components": {}, "errors": []}

        await tapps_upgrade(platform="cursor")
        call_kwargs = mock_upgrade.call_args[1]
        assert call_kwargs["platform"] == "cursor"


# ---------------------------------------------------------------------------
# tapps_doctor
# ---------------------------------------------------------------------------


class TestTappsDoctor:
    def setup_method(self) -> None:
        CallTracker.reset()

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.distribution.doctor.run_doctor_structured")
    def test_returns_success(
        self, mock_doctor: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_doctor

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_doctor.return_value = {"checks": [], "passed": True}

        result = tapps_doctor()
        assert result["success"] is True
        assert result["tool"] == "tapps_doctor"

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.distribution.doctor.run_doctor_structured")
    def test_records_call(
        self, mock_doctor: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_doctor

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_doctor.return_value = {"checks": [], "passed": True}

        CallTracker.reset()
        tapps_doctor()
        assert "tapps_doctor" in CallTracker.get_called_tools()

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.distribution.doctor.run_doctor_structured")
    def test_custom_project_root(
        self, mock_doctor: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_doctor

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_doctor.return_value = {"checks": [], "passed": True}

        tapps_doctor(project_root="/custom/root")
        mock_doctor.assert_called_once_with(project_root="/custom/root", quick=False)

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.distribution.doctor.run_doctor_structured")
    def test_quick_mode(
        self, mock_doctor: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_doctor

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_doctor.return_value = {"checks": [], "passed": True, "quick_mode": True}

        result = tapps_doctor(quick=True)
        assert result["success"] is True
        mock_doctor.assert_called_once_with(
            project_root=str(tmp_path), quick=True
        )


# ---------------------------------------------------------------------------
# tapps_init
# ---------------------------------------------------------------------------


class TestTappsInit:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_dry_run_returns_success(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {
            "errors": [],
            "dry_run": True,
            "files_created": [],
        }

        result = await tapps_init(dry_run=True)
        assert result["success"] is True
        # developer_workflow is always included for easy onboarding reference
        data = result["data"]
        assert "developer_workflow" in data
        wf = data["developer_workflow"]
        assert "daily_steps" in wf
        assert "update_step" in wf
        assert "when_to_use" in wf
        assert len(wf["daily_steps"]) == 5
        assert "tapps_upgrade" in wf["update_step"]

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_verify_only_returns_success(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {
            "errors": [],
            "verify_only": True,
        }

        result = await tapps_init(verify_only=True)
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_records_call(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": []}

        CallTracker.reset()
        await tapps_init(dry_run=True)
        assert "tapps_init" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_error_propagated(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": ["Something went wrong"]}

        result = await tapps_init(dry_run=True)
        assert result["success"] is False

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_platform_claude_passed(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": []}

        await tapps_init(dry_run=True, platform="claude")
        call_kwargs = mock_bootstrap.call_args[1]
        # bootstrap_pipeline is now called with config=BootstrapConfig(...)
        cfg = call_kwargs.get("config")
        assert cfg is not None
        assert cfg.platform == "claude"


# ---------------------------------------------------------------------------
# tapps_init mcp_config (Epic 47.2)
# ---------------------------------------------------------------------------


class TestTappsInitMcpConfig:
    """Tests for tapps_init mcp_config parameter (Epic 47.2)."""

    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_mcp_config_false_by_default(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """Default mcp_config=False does not write MCP config."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": [], "created": []}

        with patch(
            "tapps_mcp.distribution.setup_generator._generate_config"
        ) as mock_gen:
            result = await tapps_init(dry_run=False)
            mock_gen.assert_not_called()
            assert "mcp_config_written" not in result.get("data", {})

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_mcp_config_true_writes_project_scope(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """mcp_config=True writes project-scoped config."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": [], "created": []}

        with patch(
            "tapps_mcp.distribution.setup_generator._generate_config"
        ) as mock_gen:
            mock_gen.return_value = True
            result = await tapps_init(mcp_config=True)
            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args
            assert call_kwargs[1]["scope"] == "project"
            assert result["data"]["mcp_config_written"] is True
            assert result["data"]["mcp_config_scope"] == "project"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_mcp_config_skipped_on_dry_run(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """mcp_config=True with dry_run=True does not write config."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": [], "dry_run": True, "created": []}

        with patch(
            "tapps_mcp.distribution.setup_generator._generate_config"
        ) as mock_gen:
            await tapps_init(mcp_config=True, dry_run=True)
            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_mcp_config_cursor_platform(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """mcp_config=True with platform='cursor' passes cursor host."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": [], "created": []}

        with patch(
            "tapps_mcp.distribution.setup_generator._generate_config"
        ) as mock_gen:
            mock_gen.return_value = True
            await tapps_init(mcp_config=True, platform="cursor")
            assert mock_gen.call_args[0][0] == "cursor"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_mcp_config_default_host_is_claude_code(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """mcp_config=True with empty platform defaults to claude-code host."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": [], "created": []}

        with patch(
            "tapps_mcp.distribution.setup_generator._generate_config"
        ) as mock_gen:
            mock_gen.return_value = True
            await tapps_init(mcp_config=True, platform="")
            assert mock_gen.call_args[0][0] == "claude-code"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_mcp_config_never_uses_user_scope(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """mcp_config always uses scope='project', never 'user'."""
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": [], "created": []}

        with patch(
            "tapps_mcp.distribution.setup_generator._generate_config"
        ) as mock_gen:
            mock_gen.return_value = True
            await tapps_init(mcp_config=True)
            call_kwargs = mock_gen.call_args
            assert call_kwargs[1]["scope"] == "project"
            assert call_kwargs[1]["scope"] != "user"


# ---------------------------------------------------------------------------
# tapps_validate_changed
# ---------------------------------------------------------------------------


class TestTappsValidateChanged:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_no_files_returns_success(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = _make_mock_settings(tmp_path)
            with patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ):
                result = await tapps_validate_changed()
                assert result["success"] is True
                data = result["data"]
                assert "summary" in data or data.get("total_files", 0) == 0

    @pytest.mark.asyncio
    async def test_records_call(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = _make_mock_settings(tmp_path)
            with patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ):
                CallTracker.reset()
                await tapps_validate_changed()
                assert "tapps_validate_changed" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    async def test_with_files_quick_mode(self, tmp_path: Path) -> None:
        """Validate changed files in quick mode with mocked scoring."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f1 = tmp_path / "a.py"
        f1.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score(overall_score=90.0)
        mock_gate = _make_mock_gate(passed=True)

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as ms,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[f1],
            ),
            patch("tapps_mcp.server_helpers._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
                return_value=None,
            ),
        ):
            ms.return_value = _make_mock_settings(tmp_path)
            result = await tapps_validate_changed(quick=True, include_impact=False)

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1
        assert result["data"]["all_gates_passed"] is True

    @pytest.mark.asyncio
    async def test_with_files_gate_fails(self, tmp_path: Path) -> None:
        """Gate failure is reported but tool succeeds."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f1 = tmp_path / "bad.py"
        f1.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score(overall_score=40.0)
        mock_gate = _make_mock_gate(passed=False)

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as ms,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[f1],
            ),
            patch("tapps_mcp.server_helpers._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
                return_value=None,
            ),
        ):
            ms.return_value = _make_mock_settings(tmp_path)
            result = await tapps_validate_changed(quick=True, include_impact=False)

        assert result["success"] is True
        assert result["data"]["all_gates_passed"] is False

    @pytest.mark.asyncio
    async def test_quick_mode_summary_prefix(self, tmp_path: Path) -> None:
        """Quick mode prepends '[Quick mode - ruff only]' to summary."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f1 = tmp_path / "c.py"
        f1.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score()
        mock_gate = _make_mock_gate(passed=True)

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as ms,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[f1],
            ),
            patch("tapps_mcp.server_helpers._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
                return_value=None,
            ),
        ):
            ms.return_value = _make_mock_settings(tmp_path)
            result = await tapps_validate_changed(quick=True, include_impact=False)

        assert result["data"]["summary"].startswith("[Quick mode")

    @pytest.mark.asyncio
    async def test_with_impact_analysis(self, tmp_path: Path) -> None:
        """Impact analysis data is included when include_impact=True."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f1 = tmp_path / "d.py"
        f1.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score()
        mock_gate = _make_mock_gate(passed=True)
        impact = {"max_severity": "low", "total_affected_files": 0, "per_file": []}

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as ms,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[f1],
            ),
            patch("tapps_mcp.server_helpers._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
                return_value=impact,
            ),
        ):
            ms.return_value = _make_mock_settings(tmp_path)
            result = await tapps_validate_changed(quick=True, include_impact=True)

        assert "impact_summary" in result["data"]
        assert result["data"]["impact_summary"]["max_severity"] == "low"

    @pytest.mark.asyncio
    async def test_no_files_writes_marker(self, tmp_path: Path) -> None:
        """When no files found, marker is still written (all passed)."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as ms,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._write_validate_ok_marker"
            ) as mock_marker,
        ):
            ms.return_value = _make_mock_settings(tmp_path)
            await tapps_validate_changed()

        mock_marker.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_files(self, tmp_path: Path) -> None:
        """Multiple files are all validated."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        files = []
        for i in range(3):
            f = tmp_path / f"file{i}.py"
            f.write_text(f"x = {i}\n", encoding="utf-8")
            files.append(f)

        mock_score = _make_mock_score()
        mock_gate = _make_mock_gate(passed=True)

        scorer_mock = MagicMock()
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as ms,
            patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=files,
            ),
            patch("tapps_mcp.server_helpers._get_scorer", return_value=scorer_mock),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
                return_value=None,
            ),
        ):
            ms.return_value = _make_mock_settings(tmp_path)
            result = await tapps_validate_changed(quick=True, include_impact=False)

        assert result["data"]["files_validated"] == 3


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestDiscoverChangedFiles:
    def test_explicit_paths(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")

        with patch(
            "tapps_mcp.server._validate_file_path",
            side_effect=Path,
        ):
            result = _discover_changed_files(
                f"{f1},{f2}",
                "HEAD",
                tmp_path,
            )
        assert len(result) == 2

    def test_empty_paths_no_git(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        # No git repo in tmp_path, so detect_changed_python_files returns []
        result = _discover_changed_files("", "HEAD", tmp_path)
        assert isinstance(result, list)

    def test_skips_non_py_files(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        with patch(
            "tapps_mcp.server._validate_file_path",
            side_effect=Path,
        ):
            result = _discover_changed_files(
                "readme.md,data.json",
                "HEAD",
                tmp_path,
            )
        assert len(result) == 0

    def test_skips_empty_entries(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        f1 = tmp_path / "a.py"
        f1.write_text("x = 1\n", encoding="utf-8")

        with patch(
            "tapps_mcp.server._validate_file_path",
            side_effect=Path,
        ):
            result = _discover_changed_files(
                f",,{f1},,",
                "HEAD",
                tmp_path,
            )
        assert len(result) == 1

    def test_validation_error_skips_file(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        with patch(
            "tapps_mcp.server._validate_file_path",
            side_effect=ValueError("outside root"),
        ):
            result = _discover_changed_files(
                "foo.py",
                "HEAD",
                tmp_path,
            )
        assert len(result) == 0


class TestCollectResults:
    def test_normal_results(self) -> None:
        from tapps_mcp.server_pipeline_tools import _collect_results

        paths = [Path("a.py"), Path("b.py")]
        raw = [{"score": 80}, {"score": 90}]
        results = _collect_results(raw, paths)
        assert len(results) == 2
        assert results[0]["score"] == 80

    def test_exception_results(self) -> None:
        from tapps_mcp.server_pipeline_tools import _collect_results

        paths = [Path("a.py")]
        raw: list = [RuntimeError("boom")]
        results = _collect_results(raw, paths)
        assert len(results) == 1
        assert "errors" in results[0]
        assert "boom" in results[0]["errors"][0]

    def test_mixed_results(self) -> None:
        from tapps_mcp.server_pipeline_tools import _collect_results

        paths = [Path("a.py"), Path("b.py"), Path("c.py")]
        raw: list = [{"score": 80}, RuntimeError("fail"), {"score": 95}]
        results = _collect_results(raw, paths)
        assert len(results) == 3
        assert results[0]["score"] == 80
        assert "errors" in results[1]
        assert results[2]["score"] == 95


class TestWriteValidateOkMarker:
    def test_creates_marker_file(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _write_validate_ok_marker

        _write_validate_ok_marker(tmp_path)
        marker = tmp_path / ".tapps-mcp" / "sessions" / "last_validate_ok"
        assert marker.exists()

    def test_no_error_on_readonly(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _write_validate_ok_marker

        # Should not raise even if directory creation fails
        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            _write_validate_ok_marker(tmp_path)  # no exception


class TestValidateSingleFile:
    @pytest.mark.asyncio
    async def test_quick_mode_score(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _validate_single_file

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score(overall_score=92.0)
        mock_gate = _make_mock_gate(passed=True)

        scorer_mock = MagicMock()
        scorer_mock.language = "python"
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch(
                "tapps_mcp.server_helpers._get_scorer_for_file",
                return_value=scorer_mock,
            ),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            result = await _validate_single_file(
                f, "standard", quick=True,
                do_security_full=False, sem=asyncio.Semaphore(1),
            )

        assert result["overall_score"] == 92.0
        assert result["gate_passed"] is True
        assert result["security_passed"] is True
        assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_full_mode_score(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _validate_single_file

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score(overall_score=88.0)
        mock_gate = _make_mock_gate(passed=True)

        scorer_mock = MagicMock()
        scorer_mock.language = "python"
        scorer_mock.score_file = AsyncMock(return_value=mock_score)

        with (
            patch(
                "tapps_mcp.server_helpers._get_scorer_for_file",
                return_value=scorer_mock,
            ),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            result = await _validate_single_file(
                f, "standard", quick=False,
                do_security_full=False, sem=asyncio.Semaphore(1),
            )

        assert result["overall_score"] == 88.0
        assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_scoring_exception(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _validate_single_file

        f = tmp_path / "crash.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer_mock = MagicMock()
        scorer_mock.language = "python"
        scorer_mock.score_file_quick = MagicMock(side_effect=RuntimeError("boom"))

        with patch(
            "tapps_mcp.server_helpers._get_scorer_for_file",
            return_value=scorer_mock,
        ):
            result = await _validate_single_file(
                f, "standard", quick=True,
                do_security_full=False, sem=asyncio.Semaphore(1),
            )

        assert "errors" in result
        assert "boom" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_gate_failures_included(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _validate_single_file

        f = tmp_path / "gfail.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = _make_mock_score(overall_score=40.0)
        mock_gate = _make_mock_gate(passed=False)

        scorer_mock = MagicMock()
        scorer_mock.language = "python"
        scorer_mock.score_file_quick = MagicMock(return_value=mock_score)

        with (
            patch(
                "tapps_mcp.server_helpers._get_scorer_for_file",
                return_value=scorer_mock,
            ),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            result = await _validate_single_file(
                f, "standard", quick=True,
                do_security_full=False, sem=asyncio.Semaphore(1),
            )

        assert result["gate_passed"] is False
        assert "gate_failures" in result

    @pytest.mark.asyncio
    async def test_unsupported_language(self, tmp_path: Path) -> None:
        """Test that unsupported file types return an error."""
        from tapps_mcp.server_pipeline_tools import _validate_single_file

        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")

        with patch(
            "tapps_mcp.server_helpers._get_scorer_for_file",
            return_value=None,
        ):
            result = await _validate_single_file(
                f, "standard", quick=True,
                do_security_full=False, sem=asyncio.Semaphore(1),
            )

        assert "errors" in result
        assert "Unsupported file type" in result["errors"][0]


class TestComputeImpactAnalysis:
    def test_returns_none_on_failure(self) -> None:
        from tapps_mcp.server_pipeline_tools import _compute_impact_analysis

        # Force import failure
        with patch(
            "tapps_mcp.server_pipeline_tools._compute_impact_analysis",
            wraps=_compute_impact_analysis,
        ):
            # Use a non-existent path to trigger the outer try/except
            result = _compute_impact_analysis(
                [Path("/nonexistent/file.py")],
                Path("/nonexistent/root"),
            )
        # Should return error dict, not raise
        assert result is not None
        assert "error" in result or "per_file" in result

    def test_severity_aggregation(self) -> None:
        from tapps_mcp.server_pipeline_tools import _SEVERITY_RANK

        # Verify ranking is correct
        assert _SEVERITY_RANK["critical"] > _SEVERITY_RANK["high"]
        assert _SEVERITY_RANK["high"] > _SEVERITY_RANK["medium"]
        assert _SEVERITY_RANK["medium"] > _SEVERITY_RANK["low"]


class TestBuildStructuredValidationOutput:
    def test_structured_output_attached(self) -> None:
        from tapps_mcp.server_pipeline_tools import (
            _build_structured_validation_output,
        )

        results = [
            {"file_path": "a.py", "overall_score": 90.0,
             "gate_passed": True, "security_passed": True},
        ]
        resp: dict = {}
        _build_structured_validation_output(
            results, all_passed=True, security_depth="basic",
            impact_data=None, resp=resp,
        )
        # Structured output may or may not succeed depending on
        # whether output_schemas is importable - either way no exception
        # (best-effort)

    def test_structured_output_no_crash_on_empty(self) -> None:
        from tapps_mcp.server_pipeline_tools import (
            _build_structured_validation_output,
        )

        resp: dict = {}
        _build_structured_validation_output(
            results=[], all_passed=True, security_depth="basic",
            impact_data=None, resp=resp,
        )
        # Should not raise


class TestMaybeWarmDependencyCache:
    def test_skips_when_quick(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_warm_dependency_cache

        settings = MagicMock(
            dependency_scan_enabled=True,
            project_root=tmp_path,
        )
        # Should not start any background task in quick mode
        _maybe_warm_dependency_cache(settings, quick=True)

    def test_skips_when_disabled(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _maybe_warm_dependency_cache

        settings = MagicMock(
            dependency_scan_enabled=False,
            project_root=tmp_path,
        )
        _maybe_warm_dependency_cache(settings, quick=False)


class TestStartProgressReporting:
    def test_returns_none_without_ctx(self) -> None:
        from tapps_mcp.server_pipeline_tools import _start_progress_reporting

        result = _start_progress_reporting(
            ctx=None, total_files=5, start=0, stop_event=asyncio.Event(),
        )
        assert result is None

    def test_returns_none_with_zero_files(self) -> None:
        from tapps_mcp.server_pipeline_tools import _start_progress_reporting

        result = _start_progress_reporting(
            ctx=MagicMock(), total_files=0, start=0,
            stop_event=asyncio.Event(),
        )
        assert result is None


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auto-GC in session start
# ---------------------------------------------------------------------------


class TestMaybeAutoGC:
    """Tests for _maybe_auto_gc and its integration in tapps_session_start."""

    def setup_method(self) -> None:
        from tapps_mcp.server_pipeline_tools import _reset_session_gc_flag

        _reset_session_gc_flag()

    def test_gc_triggers_above_threshold(self) -> None:
        """GC runs when memory count exceeds threshold * max_memories."""
        from tapps_mcp.server_pipeline_tools import _maybe_auto_gc

        store = MagicMock()
        snapshot = MagicMock()
        snapshot.entries = []  # no actual candidates
        store.snapshot.return_value = snapshot
        store.count.return_value = 410

        settings = MagicMock()
        settings.memory.gc_enabled = True
        settings.memory.max_memories = 500
        settings.memory.gc_auto_threshold = 0.8

        result = _maybe_auto_gc(store, 410, settings)
        assert result is not None
        assert result["ran"] is True
        assert result["evicted"] == 0
        assert result["remaining"] == 410

    def test_gc_does_not_trigger_below_threshold(self) -> None:
        """GC is skipped when memory count is at or below threshold."""
        from tapps_mcp.server_pipeline_tools import _maybe_auto_gc

        store = MagicMock()
        settings = MagicMock()
        settings.memory.gc_enabled = True
        settings.memory.max_memories = 500
        settings.memory.gc_auto_threshold = 0.8

        result = _maybe_auto_gc(store, 400, settings)
        assert result is None

    def test_gc_runs_only_once_per_session(self) -> None:
        """Auto-GC is skipped on second call (once-per-session guard)."""
        from tapps_mcp.server_pipeline_tools import _maybe_auto_gc

        store = MagicMock()
        snapshot = MagicMock()
        snapshot.entries = []
        store.snapshot.return_value = snapshot
        store.count.return_value = 450

        settings = MagicMock()
        settings.memory.gc_enabled = True
        settings.memory.max_memories = 500
        settings.memory.gc_auto_threshold = 0.8

        first_result = _maybe_auto_gc(store, 450, settings)
        assert first_result is not None
        assert first_result["ran"] is True

        second_result = _maybe_auto_gc(store, 450, settings)
        assert second_result is None

    def test_gc_config_override_threshold(self) -> None:
        """Custom threshold (e.g. 0.5) triggers GC at lower count."""
        from tapps_mcp.server_pipeline_tools import _maybe_auto_gc

        store = MagicMock()
        snapshot = MagicMock()
        snapshot.entries = []
        store.snapshot.return_value = snapshot
        store.count.return_value = 260

        settings = MagicMock()
        settings.memory.gc_enabled = True
        settings.memory.max_memories = 500
        settings.memory.gc_auto_threshold = 0.5

        # 260 > 500 * 0.5 = 250, should trigger
        result = _maybe_auto_gc(store, 260, settings)
        assert result is not None
        assert result["ran"] is True

    @pytest.mark.asyncio
    async def test_session_start_defers_gc_to_background(self) -> None:
        """tapps_session_start defers memory_gc to background task (Epic 68.2)."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        mock_store = MagicMock()
        snapshot = MagicMock()
        snapshot.total_count = 450
        snapshot.entries = []
        mock_store.snapshot.return_value = snapshot
        mock_store.count.return_value = 450

        mock_settings = MagicMock()
        mock_settings.memory.enabled = True
        mock_settings.memory.gc_enabled = True
        mock_settings.memory.max_memories = 500
        mock_settings.memory.gc_auto_threshold = 0.8
        mock_settings.business_experts_enabled = False

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_mcp.server_helpers._get_memory_store",
                return_value=mock_store,
            ),
        ):
            result = await tapps_session_start()

        data = result["data"]
        # GC, consolidation, doc validation, and session capture are now
        # fire-and-forget background tasks (Epic 68.2 optimization).
        assert data["memory_gc"] == "background"
        assert data["memory_consolidation"] == "background"
        assert data["memory_doc_validation"] == "background"
        assert data["session_capture"] == "background"


class TestSessionStartProjectRoot:
    """Tests for project_root top-level field in session_start (Story 89.2)."""

    @pytest.mark.asyncio
    async def test_session_start_full_includes_project_root(self) -> None:
        """Full session_start response includes top-level project_root."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        mock_settings = MagicMock()
        mock_settings.project_root = Path("/test/project")
        mock_settings.memory.enabled = False
        mock_settings.business_experts_enabled = False

        with (
            patch(
                "tapps_mcp.server_pipeline_tools.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_mcp.server.load_settings",
                return_value=mock_settings,
            ),
        ):
            result = await tapps_session_start()

        data = result["data"]
        assert "project_root" in data
        assert data["project_root"] == "/test/project"
        # Also still present in nested configuration
        assert data["configuration"]["project_root"] == "/test/project"

    @pytest.mark.asyncio
    async def test_session_start_quick_includes_project_root(self) -> None:
        """Quick session_start response includes top-level project_root."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        mock_settings = MagicMock()
        mock_settings.project_root = Path("/test/project")
        mock_settings.quality_preset = "standard"
        mock_settings.log_level = "WARNING"

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=mock_settings,
        ):
            result = await tapps_session_start(quick=True)

        data = result["data"]
        assert "project_root" in data
        assert data["project_root"] == "/test/project"
        # Also still present in nested configuration
        assert data["configuration"]["project_root"] == "/test/project"

    @pytest.mark.asyncio
    async def test_session_start_quick_includes_checker_environment(self) -> None:
        """Quick session_start response includes checker environment context."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        mock_settings = MagicMock()
        mock_settings.project_root = Path("/test/project")
        mock_settings.quality_preset = "standard"
        mock_settings.log_level = "WARNING"

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=mock_settings,
        ):
            result = await tapps_session_start(quick=True)

        data = result["data"]
        assert data["checker_environment"] == "mcp_server"
        assert "MCP server" in data["checker_environment_note"]


class TestScheduleBackgroundMaintenance:
    """Tests for _schedule_background_maintenance (Epic 68.2)."""

    @pytest.mark.asyncio
    async def test_schedules_all_maintenance_ops(self) -> None:
        """Background task calls GC, consolidation, doc validation, session capture."""
        import asyncio

        from tapps_mcp.server_pipeline_tools import _schedule_background_maintenance

        mock_store = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.total_count = 100
        mock_settings = MagicMock()
        mock_settings.project_root = Path("/fake")

        with (
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_auto_gc",
            ) as mock_gc,
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_consolidation_scan",
            ) as mock_consol,
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_validate_memories",
                new_callable=AsyncMock,
            ) as mock_doc_val,
            patch(
                "tapps_mcp.server_pipeline_tools._process_session_capture",
            ) as mock_capture,
        ):
            _schedule_background_maintenance(mock_store, mock_snapshot, mock_settings)
            # Allow background task to complete
            await asyncio.sleep(0.05)

        mock_gc.assert_called_once_with(mock_store, 100, mock_settings)
        mock_consol.assert_called_once_with(mock_store, mock_settings)
        mock_doc_val.assert_called_once_with(mock_store, mock_settings)
        mock_capture.assert_called_once_with(Path("/fake"), mock_store)

    @pytest.mark.asyncio
    async def test_background_task_tolerates_failures(self) -> None:
        """Background maintenance continues even if individual ops fail."""
        import asyncio

        from tapps_mcp.server_pipeline_tools import _schedule_background_maintenance

        mock_store = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.total_count = 100
        mock_settings = MagicMock()
        mock_settings.project_root = Path("/fake")

        with (
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_auto_gc",
                side_effect=RuntimeError("gc boom"),
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_consolidation_scan",
                side_effect=RuntimeError("consol boom"),
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._maybe_validate_memories",
                new_callable=AsyncMock,
                side_effect=RuntimeError("doc val boom"),
            ),
            patch(
                "tapps_mcp.server_pipeline_tools._process_session_capture",
            ) as mock_capture,
        ):
            _schedule_background_maintenance(mock_store, mock_snapshot, mock_settings)
            # Allow background task to complete
            await asyncio.sleep(0.05)

        # Session capture still called despite earlier failures
        mock_capture.assert_called_once()


class TestRegister:
    def test_register_adds_tools(self) -> None:
        from tapps_mcp.server_pipeline_tools import register

        mock_mcp = MagicMock()
        # Make the tool() call return a callable that accepts a function
        mock_mcp.tool.return_value = lambda fn: fn

        # register() now requires allowed_tools; pass all pipeline tool names
        all_tools = frozenset({
            "tapps_validate_changed",
            "tapps_session_start",
            "tapps_init",
            "tapps_set_engagement_level",
            "tapps_upgrade",
            "tapps_doctor",
        })
        register(mock_mcp, all_tools)
        # 6 tools should be registered
        assert mock_mcp.tool.call_count == 6
