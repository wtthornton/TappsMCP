"""TAP-1798: tapps_feedback must actually call _adjust_domain_weights.

Previously the tool's docstring advertised domain routing — but the call
site for _adjust_domain_weights existed only at definition. The response
surfaced ``domain`` to the agent as a false signal that the routing weight
had been moved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.adaptive.persistence import DomainWeightStore
from tapps_core.config.settings import _reset_settings_cache, load_settings
from tapps_mcp.server_metrics_tools import _EXPERT_TOOLS, tapps_feedback


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def test_expert_tools_includes_lookup_docs() -> None:
    assert "tapps_lookup_docs" in _EXPERT_TOOLS


def test_feedback_for_expert_tool_with_domain_moves_store() -> None:
    """Positive feedback on an expert tool with domain must persist to the store."""
    resp = tapps_feedback(
        tool_name="tapps_lookup_docs",
        helpful=True,
        context="docs were on point",
        domain="security",
    )
    assert resp["success"] is True
    data = resp["data"]
    assert data["domain"] == "security"
    assert data["domain_weight_adjusted"] is True
    assert data["domain_weight_type"] == "technical"

    settings = load_settings()
    store = DomainWeightStore(settings.project_root)
    entry = store.get_weight("security", domain_type="technical")
    assert entry is not None, "DomainWeightStore must persist the adjustment"
    assert entry.positive_count == 1


def test_feedback_without_domain_does_not_touch_store() -> None:
    resp = tapps_feedback(
        tool_name="tapps_lookup_docs",
        helpful=True,
        context="generic feedback",
    )
    data = resp["data"]
    assert data["domain_weight_adjusted"] is False
    assert "domain_weight_type" not in data


def test_feedback_with_domain_but_non_expert_tool_does_not_touch_store() -> None:
    """Non-expert tool with a domain string still gets the domain echoed but no store move."""
    resp = tapps_feedback(
        tool_name="tapps_score_file",  # scoring tool, not expert
        helpful=True,
        domain="security",
    )
    data = resp["data"]
    assert data["domain"] == "security"
    assert data["domain_weight_adjusted"] is False, (
        "Non-expert tools must NOT move DomainWeightStore even when a domain is passed"
    )


def test_duplicate_feedback_does_not_double_apply_domain_adjustment() -> None:
    """The dedup guard around scoring weights must also gate domain weights."""
    tapps_feedback(
        tool_name="tapps_lookup_docs",
        helpful=True,
        context="dup",
        domain="performance",
    )
    second = tapps_feedback(
        tool_name="tapps_lookup_docs",
        helpful=True,
        context="dup",
        domain="performance",
    )
    data = second["data"]
    assert data["duplicate_skipped"] is True
    assert data["domain_weight_adjusted"] is False

    settings = load_settings()
    store = DomainWeightStore(settings.project_root)
    entry = store.get_weight("performance", domain_type="technical")
    assert entry is not None
    assert entry.samples == 1, (
        "Duplicate feedback should not double-apply the domain weight adjustment"
    )
