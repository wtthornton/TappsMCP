"""Integration tests for the pipeline orchestration system."""

from tapps_mcp.pipeline.models import STAGE_TOOLS, PipelineStage
from tapps_mcp.prompts.prompt_loader import (
    list_stages,
    load_overview,
    load_stage_prompt,
)


class TestStageConsistency:
    """Pipeline stages are consistent across all surfaces."""

    def test_model_stages_match_loader_stages(self):
        model_stages = [s.value for s in PipelineStage]
        loader_stages = list_stages()
        assert model_stages == loader_stages

    def test_stage_tools_cover_all_stages(self):
        for stage in PipelineStage:
            assert stage in STAGE_TOOLS, f"Missing tools for stage {stage.value}"

    def test_stage_order_matches_prompts(self):
        stages = list_stages()
        # Verify order: discover -> research -> develop -> validate -> verify
        assert stages.index("discover") < stages.index("research")
        assert stages.index("research") < stages.index("develop")
        assert stages.index("develop") < stages.index("validate")
        assert stages.index("validate") < stages.index("verify")


class TestPromptContent:
    """Stage prompt content is valid and references real tools."""

    def test_all_stage_prompts_reference_allowed_tools(self):
        for stage_name in list_stages():
            content = load_stage_prompt(stage_name)
            stage = PipelineStage(stage_name)
            tools = STAGE_TOOLS[stage]
            # At least one tool from the stage should appear in the prompt
            found = any(tool in content for tool in tools)
            assert found, f"Stage {stage_name} prompt doesn't reference its allowed tools"

    def test_stage_prompts_under_token_budget(self):
        for stage_name in list_stages():
            content = load_stage_prompt(stage_name)
            # Rough token estimate: 1 token per ~4 chars
            token_estimate = len(content) // 4
            assert token_estimate < 2000, (
                f"Stage {stage_name} prompt ~{token_estimate} tokens, exceeds 2000 budget"
            )

    def test_overview_under_token_budget(self):
        content = load_overview()
        token_estimate = len(content) // 4
        assert token_estimate < 2000, f"Overview ~{token_estimate} tokens, exceeds 2000 budget"

    def test_overview_references_all_stages(self):
        content = load_overview()
        for stage_name in list_stages():
            assert stage_name.capitalize() in content or stage_name in content


class TestPlatformRules:
    def test_claude_rules_under_token_budget(self):
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        content = load_platform_rules("claude")
        token_estimate = len(content) // 4
        assert token_estimate < 1200, f"Claude rules ~{token_estimate} tokens, exceeds 1200 budget"

    def test_cursor_rules_under_token_budget(self):
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        content = load_platform_rules("cursor")
        token_estimate = len(content) // 4
        assert token_estimate < 1200, f"Cursor rules ~{token_estimate} tokens, exceeds 1200 budget"

    def test_claude_rules_contain_enforcement_language(self):
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        content = load_platform_rules("claude")
        assert "BLOCKING REQUIREMENT" in content
        assert "MUST" in content
        assert "NEVER" in content
        assert "REQUIRED" in content

    def test_cursor_rules_contain_enforcement_language(self):
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        content = load_platform_rules("cursor")
        assert "BLOCKING REQUIREMENT" in content
        assert "MUST" in content
        assert "NEVER" in content
        assert "REQUIRED" in content


class TestHandoffRoundTrip:
    """Test full pipeline: create templates -> populate -> parse."""

    def test_init_creates_parseable_handoff(self, tmp_path):
        from tapps_mcp.pipeline.handoff import parse_handoff
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        bootstrap_pipeline(tmp_path)
        handoff_path = tmp_path / "docs" / "TAPPS_HANDOFF.md"
        assert handoff_path.exists()
        content = handoff_path.read_text()
        # Template should be parseable without errors
        state = parse_handoff(content)
        assert state is not None

    def test_init_then_render_then_parse(self, tmp_path):
        from datetime import datetime

        from tapps_mcp.pipeline.handoff import parse_handoff, render_handoff
        from tapps_mcp.pipeline.models import HandoffState, StageResult

        state = HandoffState(
            current_stage=PipelineStage.RESEARCH,
            objective="Implement OAuth",
            stage_results=[
                StageResult(
                    stage=PipelineStage.DISCOVER,
                    completed_at=datetime(2026, 2, 1, 9, 0, 0),
                    tools_called=["tapps_server_info", "tapps_project_profile"],
                    findings=["FastAPI project", "No auth currently"],
                    decisions=["Use strict quality preset"],
                ),
            ],
            next_stage_instructions="Look up OAuth2 patterns with tapps_lookup_docs",
        )

        md = render_handoff(state)
        parsed = parse_handoff(md)

        assert parsed.objective == "Implement OAuth"
        assert len(parsed.stage_results) == 1
        assert parsed.stage_results[0].stage == PipelineStage.DISCOVER
        assert "FastAPI project" in parsed.stage_results[0].findings
