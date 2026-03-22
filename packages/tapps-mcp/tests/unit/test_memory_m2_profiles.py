"""Tests for Epic M2: Memory profile & lifecycle management actions."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


@pytest.fixture()
def _reset_caches():
    """Reset singletons after each test."""
    yield
    from tapps_mcp.server_helpers import _reset_memory_store_cache, _reset_scorer_cache

    _reset_memory_store_cache()
    _reset_scorer_cache()


@pytest.fixture()
def _mock_profile_module():
    """Inject a fake tapps_brain.profile module into sys.modules."""
    mod = types.ModuleType("tapps_brain.profile")
    mod.list_builtin_profiles = MagicMock(  # type: ignore[attr-defined]
        return_value=["repo-brain", "personal-assistant", "customer-support",
                      "research-knowledge", "project-management", "home-automation"]
    )
    mod.get_builtin_profile = MagicMock(  # type: ignore[attr-defined]
        side_effect=lambda name: _make_mock_profile(name)
    )
    old = sys.modules.get("tapps_brain.profile")
    sys.modules["tapps_brain.profile"] = mod
    yield mod
    if old is not None:
        sys.modules["tapps_brain.profile"] = old
    else:
        sys.modules.pop("tapps_brain.profile", None)


def _make_mock_profile(name: str = "repo-brain", num_layers: int = 4) -> MagicMock:
    """Create a mock MemoryProfile."""
    layers = []
    layer_specs = [
        ("architectural", 180, "exponential", 0.10),
        ("pattern", 60, "exponential", 0.10),
        ("procedural", 30, "exponential", 0.10),
        ("context", 14, "exponential", 0.05),
    ]
    for i in range(min(num_layers, len(layer_specs))):
        lname, half_life, decay, floor = layer_specs[i]
        layer = MagicMock()
        layer.name = lname
        layer.description = f"Test {lname} layer"
        layer.half_life_days = half_life
        layer.decay_model = decay
        layer.confidence_floor = floor
        layer.promotion_to = layer_specs[i - 1][0] if i > 0 else None
        layer.demotion_to = layer_specs[i + 1][0] if i < len(layer_specs) - 1 else None
        layers.append(layer)

    profile = MagicMock()
    profile.name = name
    profile.description = f"Test profile: {name}"
    profile.layers = layers
    profile.scoring.relevance_weight = 0.40
    profile.scoring.confidence_weight = 0.30
    profile.scoring.recency_weight = 0.15
    profile.scoring.frequency_weight = 0.15
    profile.limits.max_entries = 1500
    profile.limits.max_value_length = 4096
    return profile


# ---------------------------------------------------------------------------
# profile_info action
# ---------------------------------------------------------------------------


class TestProfileInfoAction:
    """Tests for tapps_memory(action='profile_info')."""

    @pytest.mark.usefixtures("_reset_caches")
    def test_profile_info_with_profile(self, tmp_path: Path) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_profile = _make_mock_profile()
        mock_store = MagicMock()
        type(mock_store).profile = PropertyMock(return_value=mock_profile)
        mock_store.project_root = tmp_path
        mock_store.snapshot.return_value = MagicMock(total_count=10, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_info")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "profile_info"
        assert data["active_profile"] == "repo-brain"
        assert data["source"] == "default"
        assert len(data["layers"]) == 4
        assert data["layers"][0]["name"] == "architectural"
        assert data["layers"][0]["half_life_days"] == 180
        assert data["scoring_weights"]["relevance"] == 0.40

    @pytest.mark.usefixtures("_reset_caches")
    def test_profile_info_no_profile(self) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_store = MagicMock()
        type(mock_store).profile = PropertyMock(return_value=None)
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_info")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["active_profile"] == "repo-brain"
        assert data["source"] == "default"
        assert data["promotion_enabled"] is False

    @pytest.mark.usefixtures("_reset_caches")
    def test_profile_info_detects_project_override(self, tmp_path: Path) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        # Create project override file
        (tmp_path / ".tapps-brain").mkdir()
        (tmp_path / ".tapps-brain" / "profile.yaml").write_text("profile:\n  name: custom\n")

        mock_profile = _make_mock_profile("custom")
        mock_store = MagicMock()
        type(mock_store).profile = PropertyMock(return_value=mock_profile)
        mock_store.project_root = tmp_path
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_info")
            )

        assert result["data"]["source"] == "project_override"


# ---------------------------------------------------------------------------
# profile_list action
# ---------------------------------------------------------------------------


class TestProfileListAction:
    """Tests for tapps_memory(action='profile_list')."""

    @pytest.mark.usefixtures("_reset_caches")
    def test_profile_list_returns_profiles(self) -> None:
        """Test that profile_list returns at least a default profile."""
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_store = MagicMock()
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_list")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "profile_list"
        assert data["total"] >= 1
        names = [p["name"] for p in data["profiles"]]
        assert "repo-brain" in names

    @pytest.mark.usefixtures("_reset_caches", "_mock_profile_module")
    def test_profile_list_with_profiles_module(self) -> None:
        """Test profile_list when tapps_brain.profile is available."""
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_store = MagicMock()
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_list")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["total"] >= 6
        names = [p["name"] for p in data["profiles"]]
        assert "repo-brain" in names
        assert "research-knowledge" in names


# ---------------------------------------------------------------------------
# profile_switch action
# ---------------------------------------------------------------------------


class TestProfileSwitchAction:
    """Tests for tapps_memory(action='profile_switch')."""

    @pytest.mark.usefixtures("_reset_caches")
    def test_profile_switch_missing_value(self) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_store = MagicMock()
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_switch", value="")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["error"] == "missing_value"

    @pytest.mark.usefixtures("_reset_caches", "_mock_profile_module")
    def test_profile_switch_unknown_profile(self) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_store = MagicMock()
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_switch", value="nonexistent-profile")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["error"] == "unknown_profile"

    @pytest.mark.usefixtures("_reset_caches", "_mock_profile_module")
    def test_profile_switch_same_profile(self) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_profile = _make_mock_profile("repo-brain")
        mock_store = MagicMock()
        type(mock_store).profile = PropertyMock(return_value=mock_profile)
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_switch", value="repo-brain")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["changed"] is False
        assert data["active_profile"] == "repo-brain"

    @pytest.mark.usefixtures("_reset_caches", "_mock_profile_module")
    def test_profile_switch_success(self, tmp_path: Path) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_profile = _make_mock_profile("repo-brain")
        mock_store = MagicMock()
        type(mock_store).profile = PropertyMock(return_value=mock_profile)
        mock_store.project_root = tmp_path
        mock_store.snapshot.return_value = MagicMock(total_count=5, tier_counts={"pattern": 5})

        # After reset, the new store also needs to return valid data
        new_store = MagicMock()
        new_store.snapshot.return_value = MagicMock(total_count=5, tier_counts={"pattern": 5})

        call_count = 0

        def get_store_side_effect():
            nonlocal call_count
            call_count += 1
            return mock_store if call_count <= 1 else new_store

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            side_effect=get_store_side_effect,
        ), patch(
            "tapps_mcp.server_helpers._reset_memory_store_cache"
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_switch", value="research-knowledge")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "profile_switch"
        assert data["changed"] is True
        assert data["previous_profile"] == "repo-brain"
        assert data["active_profile"] == "research-knowledge"

    @pytest.mark.usefixtures("_reset_caches")
    def test_profile_switch_degraded_without_module(self) -> None:
        """When tapps_brain.profile is not available, return unsupported error."""
        from tapps_mcp.server_memory_tools import tapps_memory

        mock_store = MagicMock()
        mock_store.snapshot.return_value = MagicMock(total_count=0, tier_counts={})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            # Don't mock tapps_brain.profile -- let the ImportError happen naturally
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="profile_switch", value="research-knowledge")
            )

        assert result["success"] is True
        data = result["data"]
        # Either "unsupported" (ImportError) or it works if module exists
        assert data.get("error") == "unsupported" or data.get("changed") is True


# ---------------------------------------------------------------------------
# Promotion surfacing in reinforce
# ---------------------------------------------------------------------------


class TestReinforcePromotionSurfacing:
    """Tests for M2.6: promotion events surfaced in reinforce responses."""

    @pytest.mark.usefixtures("_reset_caches")
    def test_reinforce_without_promotion(self) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        entry = MagicMock()
        entry.key = "test-key"
        entry.confidence = 0.5
        entry.tier = "pattern"
        entry.model_dump.return_value = {"key": "test-key", "confidence": 0.6}

        mock_store = MagicMock()
        mock_store.get.return_value = entry
        mock_store.update_fields.return_value = entry
        type(mock_store).profile = PropertyMock(return_value=None)
        mock_store.snapshot.return_value = MagicMock(total_count=1, tier_counts={"pattern": 1})

        with patch("tapps_mcp.server_memory_tools._record_call"), patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            return_value=None,
        ), patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=mock_store,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                tapps_memory(action="reinforce", key="test-key")
            )

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "reinforce"
        assert data["found"] is True
        # No promotion when profile is None
        assert "promoted" not in data

    @pytest.mark.usefixtures("_reset_caches")
    def test_reinforce_with_promotion(self) -> None:
        from tapps_mcp.server_memory_tools import tapps_memory

        entry = MagicMock()
        entry.key = "test-key"
        entry.confidence = 0.5
        entry.tier = "context"
        entry.model_dump.return_value = {"key": "test-key", "confidence": 0.6}

        mock_profile = _make_mock_profile()
        mock_store = MagicMock()
        mock_store.get.return_value = entry
        mock_store.update_fields.return_value = entry
        type(mock_store).profile = PropertyMock(return_value=mock_profile)
        mock_store.snapshot.return_value = MagicMock(total_count=1, tier_counts={"context": 1})

        # Inject mock promotion module
        mock_engine = MagicMock()
        mock_engine.check_promotion.return_value = "procedural"

        promotion_mod = types.ModuleType("tapps_brain.promotion")
        promotion_mod.PromotionEngine = MagicMock(return_value=mock_engine)  # type: ignore[attr-defined]
        old_mod = sys.modules.get("tapps_brain.promotion")
        sys.modules["tapps_brain.promotion"] = promotion_mod

        try:
            with patch("tapps_mcp.server_memory_tools._record_call"), patch(
                "tapps_mcp.server_memory_tools.ensure_session_initialized",
                return_value=None,
            ), patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                return_value=mock_store,
            ):
                result = asyncio.get_event_loop().run_until_complete(
                    tapps_memory(action="reinforce", key="test-key")
                )

            assert result["success"] is True
            data = result["data"]
            assert data["promoted"] == "context -> procedural"
        finally:
            if old_mod is not None:
                sys.modules["tapps_brain.promotion"] = old_mod
            else:
                sys.modules.pop("tapps_brain.promotion", None)


# ---------------------------------------------------------------------------
# MemorySettings.profile field
# ---------------------------------------------------------------------------


class TestMemorySettingsProfile:
    """Tests for the new profile field in MemorySettings."""

    def test_default_profile_empty(self) -> None:
        from tapps_core.config.settings import MemorySettings

        settings = MemorySettings()
        assert settings.profile == ""

    def test_profile_override(self) -> None:
        from tapps_core.config.settings import MemorySettings

        settings = MemorySettings(profile="research-knowledge")
        assert settings.profile == "research-knowledge"
