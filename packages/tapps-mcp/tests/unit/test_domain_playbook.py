"""Tests for tapps_domain_playbook MCP tool."""

from __future__ import annotations

import pytest

from tapps_mcp.tools.domain_playbook import build_domain_playbook_payload


class TestDomainPlaybookPayload:
    def test_known_domain_deterministic(self) -> None:
        first = build_domain_playbook_payload("testing-strategies")
        second = build_domain_playbook_payload("testing-strategies")
        assert first == second
        assert first["ok"] is True
        assert first["domain"] == "testing-strategies"
        assert "pytest" in first["playbook_markdown"].lower()
        assert first["checklist_task_type"] == "qa"
        assert "tapps_diff_impact" in first["recommended_tools"]

    def test_alias_frontend(self) -> None:
        payload = build_domain_playbook_payload("frontend")
        assert payload["ok"] is True
        assert payload["domain"] == "user-experience"

    def test_unknown_domain(self) -> None:
        payload = build_domain_playbook_payload("nope")
        assert payload["ok"] is False
        assert payload["error"] == "unknown_domain"
        assert payload["did_you_mean"] == [] or isinstance(payload["did_you_mean"], list)

    def test_without_tool_sequence(self) -> None:
        payload = build_domain_playbook_payload("security", include_tool_sequence=False)
        assert "recommended_tools" not in payload
        assert "tool_sequence" not in payload
