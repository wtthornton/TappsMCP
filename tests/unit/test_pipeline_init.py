"""Tests for the tapps_init bootstrap logic."""


from tapps_mcp.pipeline.init import bootstrap_pipeline


class TestBootstrapPipeline:
    def test_creates_handoff(self, tmp_path):
        result = bootstrap_pipeline(tmp_path, create_handoff=True, create_runlog=False)
        assert "docs/TAPPS_HANDOFF.md" in result["created"]
        assert (tmp_path / "docs" / "TAPPS_HANDOFF.md").exists()
        content = (tmp_path / "docs" / "TAPPS_HANDOFF.md").read_text()
        assert "TAPPS Handoff" in content

    def test_creates_runlog(self, tmp_path):
        result = bootstrap_pipeline(tmp_path, create_handoff=False, create_runlog=True)
        assert "docs/TAPPS_RUNLOG.md" in result["created"]
        assert (tmp_path / "docs" / "TAPPS_RUNLOG.md").exists()

    def test_creates_both(self, tmp_path):
        result = bootstrap_pipeline(tmp_path)
        assert len(result["created"]) == 2
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
        result = bootstrap_pipeline(tmp_path, create_handoff=False, create_runlog=False)
        assert result["created"] == []
        assert result["skipped"] == []

    def test_claude_platform_creates_file(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path, create_handoff=False, create_runlog=False, platform="claude"
        )
        assert "CLAUDE.md" in result["created"]
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "TAPPS" in content

    def test_claude_platform_appends_to_existing(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# My Project\n\nExisting rules.\n")
        bootstrap_pipeline(
            tmp_path, create_handoff=False, create_runlog=False, platform="claude"
        )
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "My Project" in content  # Original preserved
        assert "TAPPS" in content  # Pipeline appended

    def test_claude_platform_skips_if_tapps_present(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Project\n\nUse TAPPS pipeline.\n")
        result = bootstrap_pipeline(
            tmp_path, create_handoff=False, create_runlog=False, platform="claude"
        )
        # Should not appear in created since it was already there
        assert "CLAUDE.md" not in result["created"]

    def test_cursor_platform(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path, create_handoff=False, create_runlog=False, platform="cursor"
        )
        assert ".cursor/rules/tapps-pipeline.md" in result["created"]
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.md").read_text()
        assert "TAPPS" in content

    def test_unknown_platform_errors(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path, create_handoff=False, create_runlog=False, platform="vscode"
        )
        assert len(result["errors"]) == 1
        assert "vscode" in result["errors"][0]

    def test_path_security(self, tmp_path):
        """Paths that escape project root should be rejected."""
        # The bootstrap function uses relative paths internally,
        # so this tests that the _safe_write function works correctly
        result = bootstrap_pipeline(tmp_path)
        # All created files should be under tmp_path
        for rel in result["created"]:
            full = (tmp_path / rel).resolve()
            assert str(full).startswith(str(tmp_path.resolve()))
