"""Stem coverage + smoke tests for server_linear_tools_keys (TAP-5606)."""

from __future__ import annotations

from tapps_mcp.server_linear_tools_keys import (
    _canonical_state,
    _extract_status_type,
    _fetch_hint_for_state,
    _filter_hash,
    _is_cache_bucket_alias,
    _list_issues_pass_payload,
    _resolve_cache_key,
    _ttl_for_state,
)


def test_canonical_state_collapses_open_aliases() -> None:
    assert _canonical_state("") == "open"
    assert _canonical_state("backlog") == "open"
    assert _canonical_state("COMPLETED") == "completed"


def test_filter_hash_is_stable_for_equivalent_kwargs() -> None:
    assert _filter_hash(state="open", label="") == _filter_hash(label=None, state="open")


def test_resolve_cache_key_ignores_limit_and_canonicalizes() -> None:
    a = _resolve_cache_key("T", "P", "backlog", "", 50)
    b = _resolve_cache_key("T", "P", "started", "", 999)
    assert a == b


def test_ttl_for_state_defaults_to_open_bucket() -> None:
    assert _ttl_for_state(None, 100, 200) == 100
    assert _ttl_for_state("canceled", 100, 200) == 200


def test_is_cache_bucket_alias_detects_open_and_closed() -> None:
    assert _is_cache_bucket_alias("open") is True
    assert _is_cache_bucket_alias("backlog") is False


def test_fetch_hint_for_state_warns_on_alias() -> None:
    hint = _fetch_hint_for_state("open")
    assert "cache bucket" in hint
    assert "mcp__plugin_linear_linear__list_issues" not in hint
    assert "server id varies by host" in hint


def test_fetch_hint_default_is_host_neutral() -> None:
    hint = _fetch_hint_for_state("backlog")
    assert "list_issues" in hint
    assert "mcp__plugin_linear_linear__list_issues" not in hint
    assert "server id varies by host" in hint


def test_list_issues_pass_payload_flags_alias() -> None:
    data, steps = _list_issues_pass_payload("open")
    assert "alias_warning" in data
    assert steps
    joined = data["message"] + " ".join(steps)
    assert "mcp__plugin_linear_linear__list_issues" not in joined
    assert "server id varies by host" in joined


def test_list_issues_pass_payload_concrete_state_host_neutral() -> None:
    data, steps = _list_issues_pass_payload("backlog")
    joined = data["message"] + " ".join(steps)
    assert "mcp__plugin_linear_linear__list_issues" not in joined
    assert "list_issues" in joined


def test_extract_status_type_reads_state_dict() -> None:
    assert _extract_status_type({"state": {"type": "Backlog"}}) == "backlog"
    assert _extract_status_type({}) == ""
