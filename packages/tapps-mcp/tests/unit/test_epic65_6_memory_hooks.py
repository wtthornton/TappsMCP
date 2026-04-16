"""Tests for Epic 65.6: Hook Integration in tapps_init.

Verifies memory_hooks config in .tapps-mcp.yaml, engagement defaults,
and auto-recall/auto-capture hook generation when enabled.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_mcp.pipeline.init import (
    BootstrapConfig,
    _ensure_memory_hooks_config,
    _memory_hooks_defaults_for_engagement,
    bootstrap_pipeline,
)


class TestMemoryHooksDefaultsForEngagement:
    """Engagement-level defaults for memory_hooks."""

    def test_high_enables_both(self) -> None:
        d = _memory_hooks_defaults_for_engagement("high")
        assert d["auto_recall"]["enabled"] is True
        assert d["auto_capture"]["enabled"] is True

    def test_medium_enables_auto_recall_only(self) -> None:
        d = _memory_hooks_defaults_for_engagement("medium")
        assert d["auto_recall"]["enabled"] is True
        assert d["auto_capture"]["enabled"] is False

    def test_low_disables_both(self) -> None:
        d = _memory_hooks_defaults_for_engagement("low")
        assert d["auto_recall"]["enabled"] is False
        assert d["auto_capture"]["enabled"] is False

    def test_high_has_max_results_and_min_score(self) -> None:
        d = _memory_hooks_defaults_for_engagement("high")
        assert d["auto_recall"]["max_results"] == 5
        assert d["auto_recall"]["min_score"] == 0.3
        assert d["auto_capture"]["max_facts"] == 5


class TestEnsureMemoryHooksConfig:
    """Ensure memory_hooks section in .tapps-mcp.yaml."""

    def test_creates_yaml_with_memory_hooks_when_missing(self, tmp_path: Path) -> None:
        action = _ensure_memory_hooks_config(tmp_path, "high", dry_run=False)
        yaml_path = tmp_path / ".tapps-mcp.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text())
        assert "memory_hooks" in data
        assert data["memory_hooks"]["auto_recall"]["enabled"] is True
        assert data["memory_hooks"]["auto_capture"]["enabled"] is True
        assert action in ("created", "updated")

    def test_merges_into_existing_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / ".tapps-mcp.yaml"
        yaml_path.write_text("quality_preset: strict\n", encoding="utf-8")
        action = _ensure_memory_hooks_config(tmp_path, "medium", dry_run=False)
        data = yaml.safe_load(yaml_path.read_text())
        assert data["quality_preset"] == "strict"
        assert "memory_hooks" in data
        assert data["memory_hooks"]["auto_recall"]["enabled"] is True
        assert data["memory_hooks"]["auto_capture"]["enabled"] is False

    def test_skips_on_dry_run(self, tmp_path: Path) -> None:
        action = _ensure_memory_hooks_config(tmp_path, "high", dry_run=True)
        assert action == "skipped"
        assert not (tmp_path / ".tapps-mcp.yaml").exists()


class TestBootstrapMemoryHooksIntegration:
    """bootstrap_pipeline wires memory_hooks config and hooks."""

    def test_init_adds_memory_hooks_config_when_platform_claude(self, tmp_path: Path) -> None:
        cfg = BootstrapConfig(
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
            minimal=False,
        )
        result = bootstrap_pipeline(tmp_path, config=cfg)
        assert "memory_hooks_config" in result
        yaml_path = tmp_path / ".tapps-mcp.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text())
        assert "memory_hooks" in data

    def test_init_adds_auto_recall_hook_when_high_engagement(self, tmp_path: Path) -> None:
        # High engagement enables both auto_recall and auto_capture by default
        cfg = BootstrapConfig(
            platform="claude",
            llm_engagement_level="high",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
            minimal=False,
        )
        result = bootstrap_pipeline(tmp_path, config=cfg)
        assert "memory_hooks_config" in result
        yaml_path = tmp_path / ".tapps-mcp.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text())
        assert data.get("memory_hooks", {}).get("auto_recall", {}).get("enabled")
        # Auto-recall hook script should be generated
        script_sh = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.sh"
        script_ps1 = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.ps1"
        assert script_sh.exists() or script_ps1.exists(), (
            "auto-recall hook script should be created when enabled"
        )
