"""Tests for domain playbook registry and loader."""

from __future__ import annotations

import pytest

from tapps_core.playbooks import (
    get_playbook,
    list_domain_ids,
    load_playbook_markdown,
    load_playbook_markdown_by_domain,
    resolve_domain_id,
    suggest_domains_for_text,
)


class TestPlaybookRegistry:
    def test_list_domain_ids_stable(self) -> None:
        ids = list_domain_ids()
        assert "testing-strategies" in ids
        assert "security" in ids
        assert ids == sorted(ids)

    def test_resolve_aliases(self) -> None:
        assert resolve_domain_id("frontend") == "user-experience"
        assert resolve_domain_id("testing") == "testing-strategies"

    def test_unknown_domain(self) -> None:
        assert get_playbook("not-a-domain") is None

    def test_suggest_domains_from_title(self) -> None:
        domains = suggest_domains_for_text("Add pytest coverage for auth security epic")
        assert "testing-strategies" in domains
        assert "security" in domains


class TestPlaybookLoader:
    def test_load_testing_playbook(self) -> None:
        meta = get_playbook("testing-strategies")
        assert meta is not None
        text = load_playbook_markdown(meta)
        assert "pytest" in text.lower()

    def test_load_by_domain_alias(self) -> None:
        meta, text = load_playbook_markdown_by_domain("security")
        assert meta.domain_id == "security"
        assert "tapps_security_scan" in text

    def test_missing_file_raises(self) -> None:
        meta = get_playbook("testing-strategies")
        assert meta is not None
        broken = meta.model_copy(update={"playbook_file": "missing.md"})
        with pytest.raises(FileNotFoundError):
            load_playbook_markdown(broken)
