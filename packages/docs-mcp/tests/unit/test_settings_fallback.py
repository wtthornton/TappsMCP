"""Tests for ``.docsmcp.yaml`` defaults flowing through validator tools.

Each tool (``docs_check_drift``, ``docs_check_completeness``,
``docs_check_freshness``) should honor its project-wide setting when the
call-time argument is empty, and the explicit call-time argument should win
when both are present.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from docs_mcp.config.settings import DocsMCPSettings
from docs_mcp.validators.completeness import CompletenessReport
from docs_mcp.validators.drift import DriftReport
from docs_mcp.validators.freshness import FreshnessReport


def _settings_with(tmp_path: Path, **overrides: object) -> DocsMCPSettings:
    return DocsMCPSettings(project_root=tmp_path, **overrides)


class TestDriftSettingsFallback:
    """``settings.drift_ignore_patterns`` feeds DriftDetector.check when the
    call-time ``ignore_patterns`` is empty; the explicit arg wins otherwise."""

    @pytest.mark.asyncio
    async def test_empty_call_uses_settings_list(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(
                    tmp_path, drift_ignore_patterns=["pkg.internal.*"]
                ),
            ),
            patch("docs_mcp.validators.drift.DriftDetector") as mock_cls,
        ):
            mock_cls.return_value.check.return_value = DriftReport()
            from docs_mcp.server_val_tools import docs_check_drift

            await docs_check_drift(project_root=str(tmp_path))

        passed = mock_cls.return_value.check.call_args.kwargs["ignore_patterns"]
        assert passed == ["pkg.internal.*"]

    @pytest.mark.asyncio
    async def test_empty_call_uses_settings_defaults_sentinel(
        self, tmp_path: Path
    ) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(tmp_path, drift_ignore_patterns="defaults"),
            ),
            patch("docs_mcp.validators.drift.DriftDetector") as mock_cls,
        ):
            mock_cls.return_value.check.return_value = DriftReport()
            from docs_mcp.server_val_tools import docs_check_drift

            await docs_check_drift(project_root=str(tmp_path))

        passed = mock_cls.return_value.check.call_args.kwargs["ignore_patterns"]
        assert passed == "defaults"

    @pytest.mark.asyncio
    async def test_explicit_call_overrides_settings(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(
                    tmp_path, drift_ignore_patterns=["pkg.internal.*"]
                ),
            ),
            patch("docs_mcp.validators.drift.DriftDetector") as mock_cls,
        ):
            mock_cls.return_value.check.return_value = DriftReport()
            from docs_mcp.server_val_tools import docs_check_drift

            await docs_check_drift(
                project_root=str(tmp_path),
                ignore_patterns="cli.*",
            )

        passed = mock_cls.return_value.check.call_args.kwargs["ignore_patterns"]
        assert passed == ["cli.*"]

    @pytest.mark.asyncio
    async def test_empty_call_empty_settings_passes_none(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(tmp_path),
            ),
            patch("docs_mcp.validators.drift.DriftDetector") as mock_cls,
        ):
            mock_cls.return_value.check.return_value = DriftReport()
            from docs_mcp.server_val_tools import docs_check_drift

            await docs_check_drift(project_root=str(tmp_path))

        passed = mock_cls.return_value.check.call_args.kwargs["ignore_patterns"]
        assert passed is None


class TestCompletenessSettingsFallback:
    """``settings.completeness_exclude`` feeds CompletenessChecker.check when
    the call-time ``exclude`` is empty."""

    @pytest.mark.asyncio
    async def test_empty_call_uses_settings(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(
                    tmp_path, completeness_exclude=["vendored/**", "third_party/**"]
                ),
            ),
            patch(
                "docs_mcp.validators.completeness.CompletenessChecker"
            ) as mock_cls,
        ):
            mock_cls.return_value.check.return_value = CompletenessReport()
            from docs_mcp.server_val_tools import docs_check_completeness

            await docs_check_completeness(project_root=str(tmp_path))

        passed = mock_cls.return_value.check.call_args.kwargs["exclude"]
        assert passed == ["vendored/**", "third_party/**"]

    @pytest.mark.asyncio
    async def test_explicit_call_overrides_settings(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(
                    tmp_path, completeness_exclude=["vendored/**"]
                ),
            ),
            patch(
                "docs_mcp.validators.completeness.CompletenessChecker"
            ) as mock_cls,
        ):
            mock_cls.return_value.check.return_value = CompletenessReport()
            from docs_mcp.server_val_tools import docs_check_completeness

            await docs_check_completeness(
                project_root=str(tmp_path),
                exclude="other/**",
            )

        passed = mock_cls.return_value.check.call_args.kwargs["exclude"]
        assert passed == ["other/**"]


class TestFreshnessSettingsFallback:
    """``settings.freshness_exclude`` feeds FreshnessChecker.check when the
    call-time ``exclude`` is empty."""

    @pytest.mark.asyncio
    async def test_empty_call_uses_settings(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(
                    tmp_path, freshness_exclude=["docs/legacy/**"]
                ),
            ),
            patch("docs_mcp.validators.freshness.FreshnessChecker") as mock_cls,
        ):
            mock_cls.return_value.check.return_value = FreshnessReport()
            from docs_mcp.server_val_tools import docs_check_freshness

            await docs_check_freshness(project_root=str(tmp_path))

        passed = mock_cls.return_value.check.call_args.kwargs["exclude"]
        assert passed == ["docs/legacy/**"]

    @pytest.mark.asyncio
    async def test_explicit_call_overrides_settings(self, tmp_path: Path) -> None:
        with (
            patch(
                "docs_mcp.server_val_tools._get_settings",
                return_value=_settings_with(
                    tmp_path, freshness_exclude=["docs/legacy/**"]
                ),
            ),
            patch("docs_mcp.validators.freshness.FreshnessChecker") as mock_cls,
        ):
            mock_cls.return_value.check.return_value = FreshnessReport()
            from docs_mcp.server_val_tools import docs_check_freshness

            await docs_check_freshness(
                project_root=str(tmp_path),
                exclude="other/**",
            )

        passed = mock_cls.return_value.check.call_args.kwargs["exclude"]
        assert passed == ["other/**"]
