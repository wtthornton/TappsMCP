"""Tests for business expert integration in tapps_init (Story 45.2)."""

from __future__ import annotations

from unittest.mock import patch

from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline


def _minimal_cfg(**overrides: object) -> BootstrapConfig:
    """Build a minimal BootstrapConfig with all generation disabled."""
    defaults = {
        "create_handoff": False,
        "create_runlog": False,
        "create_agents_md": False,
        "create_tech_stack_md": False,
        "verify_server": False,
        "warm_cache_from_tech_stack": False,
        "warm_expert_rag_from_tech_stack": False,
        "minimal": True,
    }
    defaults.update(overrides)
    return BootstrapConfig(**defaults)  # type: ignore[arg-type]


_VALID_EXPERTS_YAML = """\
experts:
  - expert_id: expert-billing
    expert_name: Billing Expert
    primary_domain: billing
    description: Handles billing workflows.
    keywords: [invoice, payment]
  - expert_id: expert-ops
    expert_name: Ops Expert
    primary_domain: operations
    keywords: [deploy, infra]
"""


class TestInitBusinessExperts:
    """Tests for business expert loading in bootstrap_pipeline."""

    def _run(self, tmp_path, cfg=None, experts_yaml=None):
        """Run bootstrap with mocked internals and optional experts.yaml."""
        if experts_yaml is not None:
            tapps_dir = tmp_path / ".tapps-mcp"
            tapps_dir.mkdir(parents=True, exist_ok=True)
            (tapps_dir / "experts.yaml").write_text(experts_yaml, encoding="utf-8")

        if cfg is None:
            cfg = _minimal_cfg()

        with patch(
            "tapps_mcp.pipeline.init._run_server_verification",
            return_value={"ok": True},
        ), patch(
            "tapps_mcp.pipeline.init._detect_profile",
        ):
            return bootstrap_pipeline(tmp_path, config=cfg)

    def test_no_experts_yaml_no_business_section(self, tmp_path):
        """Without experts.yaml, no business_experts section in result."""
        result = self._run(tmp_path)
        assert "business_experts" not in result

    def test_valid_experts_yaml_reports_loaded_count(self, tmp_path):
        """With valid experts.yaml, reports loaded expert count."""
        with patch(
            "tapps_core.experts.business_loader.load_settings"
        ) as mock_settings:
            mock_settings.return_value.business_experts_enabled = True
            result = self._run(tmp_path, experts_yaml=_VALID_EXPERTS_YAML)

        assert "business_experts" in result
        biz = result["business_experts"]
        assert biz["loaded"] == 2
        assert "expert-billing" in biz["expert_ids"]
        assert "expert-ops" in biz["expert_ids"]

    def test_scaffold_experts_creates_knowledge_dirs(self, tmp_path):
        """With scaffold_experts=True, creates missing knowledge dirs."""
        cfg = _minimal_cfg(scaffold_experts=True)
        with patch(
            "tapps_core.experts.business_loader.load_settings"
        ) as mock_settings:
            mock_settings.return_value.business_experts_enabled = True
            result = self._run(tmp_path, cfg=cfg, experts_yaml=_VALID_EXPERTS_YAML)

        biz = result["business_experts"]
        assert "scaffolded" in biz
        assert len(biz["scaffolded"]) >= 1

        # Check that at least one knowledge directory was created
        knowledge_base = tmp_path / ".tapps-mcp" / "knowledge"
        assert knowledge_base.exists()
        subdirs = list(knowledge_base.iterdir())
        assert len(subdirs) >= 1

    def test_dry_run_does_not_create_dirs(self, tmp_path):
        """With dry_run=True and scaffold_experts=True, no dirs created."""
        cfg = _minimal_cfg(scaffold_experts=True, dry_run=True)
        with patch(
            "tapps_core.experts.business_loader.load_settings"
        ) as mock_settings:
            mock_settings.return_value.business_experts_enabled = True
            result = self._run(tmp_path, cfg=cfg, experts_yaml=_VALID_EXPERTS_YAML)

        biz = result["business_experts"]
        # dry_run prevents scaffolding
        assert "scaffolded" not in biz

        knowledge_base = tmp_path / ".tapps-mcp" / "knowledge"
        assert not knowledge_base.exists()

    def test_invalid_experts_yaml_reports_errors_gracefully(self, tmp_path):
        """Invalid experts.yaml reports errors without failing init."""
        invalid_yaml = "experts:\n  - expert_id: bad-no-prefix\n    expert_name: Bad\n    primary_domain: bad\n"
        result = self._run(tmp_path, experts_yaml=invalid_yaml)

        # Init should still succeed overall (business expert errors are non-fatal)
        assert "business_experts" in result
        biz = result["business_experts"]
        # Either an error string or loaded=0 with errors
        has_error = "error" in biz or (biz.get("errors") and len(biz["errors"]) > 0)
        assert has_error or biz.get("loaded", 0) == 0
