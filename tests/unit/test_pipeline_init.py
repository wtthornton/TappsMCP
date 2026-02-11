"""Tests for the tapps_init bootstrap logic."""

from tapps_mcp.pipeline.init import bootstrap_pipeline


class TestBootstrapPipeline:
    def test_creates_handoff(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=True,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "docs/TAPPS_HANDOFF.md" in result["created"]
        assert (tmp_path / "docs" / "TAPPS_HANDOFF.md").exists()
        content = (tmp_path / "docs" / "TAPPS_HANDOFF.md").read_text()
        assert "TAPPS Handoff" in content

    def test_creates_runlog(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=True,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "docs/TAPPS_RUNLOG.md" in result["created"]
        assert (tmp_path / "docs" / "TAPPS_RUNLOG.md").exists()

    def test_creates_both(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert len(result["created"]) >= 2
        assert "docs/TAPPS_HANDOFF.md" in result["created"]
        assert "docs/TAPPS_RUNLOG.md" in result["created"]
        assert not result["errors"]

    def test_skips_existing_handoff(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "TAPPS_HANDOFF.md").write_text("existing content")
        result = bootstrap_pipeline(tmp_path)
        assert "docs/TAPPS_HANDOFF.md" in result["skipped"]
        # Should not overwrite
        assert (docs / "TAPPS_HANDOFF.md").read_text() == "existing content"

    def test_skips_existing_runlog(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "TAPPS_RUNLOG.md").write_text("existing log")
        result = bootstrap_pipeline(tmp_path, create_handoff=False)
        assert "docs/TAPPS_RUNLOG.md" in result["skipped"]

    def test_no_files_when_disabled(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert result["created"] == []
        assert result["skipped"] == []

    def test_claude_platform_creates_file(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="claude",
        )
        assert "CLAUDE.md" in result["created"]
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "TAPPS" in content

    def test_claude_platform_appends_to_existing(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# My Project\n\nExisting rules.\n")
        bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="claude",
        )
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "My Project" in content  # Original preserved
        assert "TAPPS" in content  # Pipeline appended

    def test_claude_platform_skips_if_tapps_present(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Project\n\nUse TAPPS pipeline.\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="claude",
        )
        # Should not appear in created since it was already there
        assert "CLAUDE.md" not in result["created"]

    def test_cursor_platform(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="cursor",
        )
        assert ".cursor/rules/tapps-pipeline.md" in result["created"]
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.md").read_text()
        assert "TAPPS" in content

    def test_unknown_platform_errors(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="vscode",
        )
        assert len(result["errors"]) == 1
        assert "vscode" in result["errors"][0]

    def test_path_security(self, tmp_path):
        """Paths that escape project root should be rejected."""
        result = bootstrap_pipeline(
            tmp_path,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        for rel in result["created"]:
            full = (tmp_path / rel).resolve()
            assert str(full).startswith(str(tmp_path.resolve()))

    def test_creates_agents_md_when_missing(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "AGENTS.md" in result["created"]
        assert result["agents_md"]["action"] == "created"
        content = (tmp_path / "AGENTS.md").read_text()
        assert "TappsMCP" in content
        assert "tapps_server_info" in content

    def test_skips_agents_md_when_exists(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Custom agents\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "AGENTS.md" in result["skipped"]
        assert result["agents_md"]["action"] == "skipped"
        assert (tmp_path / "AGENTS.md").read_text() == "# Custom agents\n"

    def test_creates_tech_stack_md(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'foo'\ndependencies = []\n"
        )
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "TECH_STACK.md" in result["created"]
        assert result["tech_stack_md"]["action"] in ("created", "updated")
        content = (tmp_path / "TECH_STACK.md").read_text()
        assert "# Tech Stack" in content
        assert "Project Type" in content

    def test_server_verification_in_result(self, tmp_path):
        result = bootstrap_pipeline(tmp_path, create_handoff=False, create_runlog=False)
        assert "server_verification" in result
        sv = result["server_verification"]
        assert "ok" in sv
        assert "installed" in sv
        assert "missing_checkers" in sv

    def test_cache_warming_in_result(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[project]\ndependencies = []\n"
        )
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=True,
            verify_server=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "cache_warming" in result
        cw = result["cache_warming"]
        assert "warmed" in cw
        assert "libraries" in cw

    def test_expert_rag_warming_in_result(self, tmp_path):
        """Expert RAG warming runs and returns expected structure."""
        (tmp_path / "pyproject.toml").write_text(
            "[project]\ndependencies = []\n"
        )
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=True,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=True,
        )
        assert "expert_rag_warming" in result
        erg = result["expert_rag_warming"]
        assert "warmed" in erg
        assert "attempted" in erg
        assert "domains" in erg
        assert isinstance(erg["domains"], list)
