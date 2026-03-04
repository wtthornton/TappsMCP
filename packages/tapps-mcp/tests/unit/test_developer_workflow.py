"""Tests for common.developer_workflow (Setup / Update / Daily content)."""

from __future__ import annotations

import pytest

from tapps_mcp.common.developer_workflow import (
    DAILY_STEPS,
    RECOMMENDED_WORKFLOW_TEXT,
    SETUP_STEPS,
    UPDATE_STEP,
    WHEN_TO_USE,
    get_developer_workflow_dict,
    render_workflow_md,
)


def test_daily_steps_count() -> None:
    assert len(DAILY_STEPS) == 5


def test_daily_steps_mention_tools() -> None:
    assert any("tapps_session_start" in s for s in DAILY_STEPS)
    assert any("tapps_quick_check" in s for s in DAILY_STEPS)
    assert any("tapps_validate_changed" in s for s in DAILY_STEPS)
    assert any("tapps_checklist" in s for s in DAILY_STEPS)


def test_recommended_workflow_text_non_empty() -> None:
    assert RECOMMENDED_WORKFLOW_TEXT
    assert "tapps_session_start" in RECOMMENDED_WORKFLOW_TEXT
    assert "tapps_checklist" in RECOMMENDED_WORKFLOW_TEXT


def test_setup_steps_count() -> None:
    assert len(SETUP_STEPS) >= 2


def test_update_step_mentions_upgrade() -> None:
    assert "tapps_upgrade" in UPDATE_STEP


def test_when_to_use_has_entries() -> None:
    assert len(WHEN_TO_USE) >= 5
    for tool, when in WHEN_TO_USE:
        assert tool.startswith("tapps_")
        assert when


def test_get_developer_workflow_dict_success() -> None:
    d = get_developer_workflow_dict(setup_done=True)
    assert d["setup_done"] is True
    assert d["daily_steps"] == list(DAILY_STEPS)
    assert d["update_step"] == UPDATE_STEP
    when = d["when_to_use"]
    assert len(when) == len(WHEN_TO_USE)
    assert all("tool" in e and "when" in e for e in when)


def test_get_developer_workflow_dict_setup_not_done() -> None:
    d = get_developer_workflow_dict(setup_done=False)
    assert d["setup_done"] is False


def test_render_workflow_md_contains_sections() -> None:
    md = render_workflow_md()
    assert "# TappsMCP developer workflow" in md
    assert "## Setup (once per project)" in md
    assert "## Update (after upgrading TappsMCP)" in md
    assert "## Daily workflow" in md
    assert "## When to use other tools" in md
    assert "tapps_upgrade" in md
    assert "tapps_session_start" in md
