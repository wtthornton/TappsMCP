"""Tests for prompt artifact generator (Epic 75)."""

from __future__ import annotations

from docs_mcp.generators.prompts import (
    COMPACT_VIEW_MAX_TOKENS,
    ContextFileEntry,
    PromptConfig,
    PromptGenerator,
    SuccessBrief,
    estimate_tokens,
)


class TestPromptConfig:
    """PromptConfig validation and serialization."""

    def test_minimal_config(self) -> None:
        config = PromptConfig(name="test-prompt", purpose_and_intent="For testing.")
        assert config.name == "test-prompt"
        assert config.purpose_and_intent == "For testing."
        assert config.task == ""
        assert config.style == "standard"

    def test_full_config(self) -> None:
        config = PromptConfig(
            name="quality-gate",
            when_to_use="Before declaring work complete.",
            purpose_and_intent="This prompt is for running the quality gate so that all files pass.",
            task="Run tapps_validate_changed and tapps_checklist.",
            success_criteria="All gates pass and checklist complete.",
            context_files=[
                ContextFileEntry(path="AGENTS.md", description="Tool usage"),
            ],
            rules="Read AGENTS.md before starting.",
            conversation_first=True,
            plan_steps=5,
            alignment_required=True,
            allowed_tools=["tapps_validate_changed", "tapps_checklist"],
            output_format="Markdown summary.",
            dont=["skip validation", "omit file_paths"],
            style="comprehensive",
        )
        assert len(config.context_files) == 1
        assert config.context_files[0].path == "AGENTS.md"
        assert config.conversation_first is True
        assert config.plan_steps == 5
        assert len(config.allowed_tools) == 2
        assert len(config.dont) == 2

    def test_success_brief_optional(self) -> None:
        config = PromptConfig(
            name="x",
            purpose_and_intent="Intent.",
            success_brief=SuccessBrief(
                output_type="Markdown",
                success_means="User approves.",
            ),
        )
        assert config.success_brief is not None
        assert config.success_brief.output_type == "Markdown"


class TestPromptGenerator:
    """PromptGenerator output shape and markers."""

    def test_generate_minimal(self) -> None:
        config = PromptConfig(
            name="minimal",
            purpose_and_intent="This prompt is for minimal testing.",
        )
        gen = PromptGenerator()
        out = gen.generate(config)
        assert "<!-- docsmcp:start:metadata -->" in out
        assert "<!-- docsmcp:start:purpose-intent -->" in out
        assert "Purpose & Intent" in out
        assert "minimal" in out
        assert "This prompt is for minimal testing." in out

    def test_generate_with_task_and_rules(self) -> None:
        config = PromptConfig(
            name="with-task",
            purpose_and_intent="For task and rules.",
            task="Do the thing.",
            success_criteria="Done when X.",
            rules="Always run Y first.",
        )
        gen = PromptGenerator()
        out = gen.generate(config)
        assert "docsmcp:start:task" in out
        assert "Do the thing." in out
        assert "docsmcp:start:rules" in out
        assert "Always run Y first." in out

    def test_generate_with_context_files(self) -> None:
        config = PromptConfig(
            name="with-context",
            purpose_and_intent="Intent.",
            context_files=[
                ContextFileEntry(path="foo.md", description="Foo content"),
                ContextFileEntry(path="bar.md", description=""),
            ],
        )
        gen = PromptGenerator()
        out = gen.generate(config)
        assert "Context files" in out
        assert "foo.md" in out
        assert "Foo content" in out
        assert "bar.md" in out

    def test_generate_with_allowed_tools_and_dont(self) -> None:
        config = PromptConfig(
            name="tools",
            purpose_and_intent="Intent.",
            allowed_tools=["tapps_session_start", "tapps_quick_check"],
            dont=["skip checklist", "omit file_paths"],
        )
        gen = PromptGenerator()
        out = gen.generate(config)
        assert "Allowed tools" in out
        assert "tapps_session_start" in out
        assert "Don't" in out
        assert "skip checklist" in out

    def test_generate_conversation_plan_alignment(self) -> None:
        config = PromptConfig(
            name="conv",
            purpose_and_intent="Intent.",
            conversation_first=True,
            plan_steps=3,
            alignment_required=True,
        )
        gen = PromptGenerator()
        out = gen.generate(config)
        assert "Conversation" in out
        assert "Plan" in out
        assert "3 steps" in out
        assert "Alignment" in out


class TestCompactView:
    """Compact LLM view (Epic 75.4): required sections and token budget."""

    def test_compact_contains_required_sections(self) -> None:
        config = PromptConfig(
            name="quality-gate",
            purpose_and_intent="This prompt is for running the quality gate so that all files pass.",
            task="Run tapps_validate_changed.",
            success_criteria="All gates pass.",
            rules="Read AGENTS.md first.",
            dont=["skip validation"],
        )
        gen = PromptGenerator()
        out = gen.generate_compact(config)
        assert "# quality-gate" in out or "quality-gate" in out
        assert "## Purpose" in out
        assert "quality gate" in out or "Purpose" in out
        assert "## Success criteria" in out
        assert "## Steps" in out
        assert "## Rules" in out
        assert "## Don't" in out
        assert "skip validation" in out

    def test_compact_under_token_budget(self) -> None:
        config = PromptConfig(
            name="sample",
            purpose_and_intent="This prompt is for testing so that compact view stays under budget.",
            task="Do the thing.",
            success_criteria="Done when X.",
            rules="Rule one. Rule two.",
            allowed_tools=["tapps_session_start", "tapps_quick_check"],
            dont=["don't skip"],
        )
        gen = PromptGenerator()
        out = gen.generate_compact(config)
        tokens = estimate_tokens(out)
        assert tokens <= COMPACT_VIEW_MAX_TOKENS, (
            f"Compact view {tokens} tokens exceeds {COMPACT_VIEW_MAX_TOKENS}"
        )

    def test_estimate_tokens_empty(self) -> None:
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0

    def test_estimate_tokens_rough(self) -> None:
        # ~10 words -> ~13-14 tokens
        text = "one two three four five six seven eight nine ten"
        assert 10 <= estimate_tokens(text) <= 20
