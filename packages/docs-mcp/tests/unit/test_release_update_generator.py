"""Tests for docs_mcp.generators.release_update."""

from __future__ import annotations

import pytest

from docs_mcp.generators.release_update import (
    ReleaseUpdateConfig,
    ReleaseUpdateGenerator,
    infer_bump_type,
    scrape_tap_refs,
)


@pytest.fixture()
def gen() -> ReleaseUpdateGenerator:
    return ReleaseUpdateGenerator()


@pytest.fixture()
def base_config() -> ReleaseUpdateConfig:
    return ReleaseUpdateConfig(
        version="1.5.0",
        prev_version="1.4.2",
        bump_type="minor",
        highlights=["Added tapps_release_update tool", "Improved changelog parsing"],
        issues_closed=["TAP-1112: tapps_release_update MCP tool", "TAP-1111: docs-mcp generator"],
        links={"Changelog": "https://example.com/CHANGELOG.md"},
        release_date="2026-04-29",
    )


class TestReleaseUpdateGenerator:
    def test_version_header_present(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        body = gen.generate(base_config)
        assert "## Release v1.5.0 (2026-04-29)" in body

    def test_health_present(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        body = gen.generate(base_config)
        assert "**Health:** On Track" in body

    def test_highlights_rendered(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        body = gen.generate(base_config)
        assert "### Highlights" in body
        assert "- Added tapps_release_update tool" in body
        assert "- Improved changelog parsing" in body

    def test_issues_closed_rendered(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        body = gen.generate(base_config)
        assert "### Issues Closed" in body
        assert "- TAP-1112: tapps_release_update MCP tool" in body

    def test_links_rendered(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        body = gen.generate(base_config)
        assert "### Links" in body
        assert "- Changelog: https://example.com/CHANGELOG.md" in body

    def test_breaking_changes_included_for_minor(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        base_config.breaking_changes = ["Removed legacy tapps_report_v1 endpoint"]
        body = gen.generate(base_config)
        assert "### Breaking Changes" in body
        assert "- Removed legacy tapps_report_v1 endpoint" in body

    def test_breaking_changes_included_for_major(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        base_config.bump_type = "major"
        base_config.breaking_changes = ["Dropped Python 3.11 support"]
        body = gen.generate(base_config)
        assert "### Breaking Changes" in body

    def test_breaking_changes_omitted_for_patch(self, gen: ReleaseUpdateGenerator) -> None:
        config = ReleaseUpdateConfig(
            version="1.4.3",
            prev_version="1.4.2",
            bump_type="patch",
            highlights=["Fixed edge case"],
            issues_closed=["TAP-999: bug fix"],
            breaking_changes=["Should not appear"],
            release_date="2026-04-29",
        )
        body = gen.generate(config)
        assert "### Breaking Changes" not in body

    def test_breaking_changes_omitted_when_empty_for_minor(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        base_config.breaking_changes = []
        body = gen.generate(base_config)
        assert "### Breaking Changes" not in body

    def test_empty_highlights_fallback(self, gen: ReleaseUpdateGenerator) -> None:
        config = ReleaseUpdateConfig(
            version="1.5.0",
            prev_version="1.4.2",
            bump_type="patch",
            highlights=[],
            issues_closed=["TAP-100: fix"],
            release_date="2026-04-29",
        )
        body = gen.generate(config)
        assert "No highlights recorded." in body

    def test_empty_issues_fallback(self, gen: ReleaseUpdateGenerator) -> None:
        config = ReleaseUpdateConfig(
            version="1.5.0",
            prev_version="1.4.2",
            bump_type="patch",
            highlights=["something"],
            issues_closed=[],
            release_date="2026-04-29",
        )
        body = gen.generate(config)
        assert "None." in body

    def test_custom_health(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        base_config.health = "At Risk"
        body = gen.generate(base_config)
        assert "**Health:** At Risk" in body

    def test_no_links_section_when_empty(self, gen: ReleaseUpdateGenerator, base_config: ReleaseUpdateConfig) -> None:
        base_config.links = {}
        body = gen.generate(base_config)
        assert "### Links" not in body

    def test_date_defaults_to_today(self, gen: ReleaseUpdateGenerator) -> None:
        config = ReleaseUpdateConfig(
            version="1.5.0",
            prev_version="1.4.2",
            bump_type="patch",
            highlights=["fix"],
            issues_closed=["TAP-1: fix"],
        )
        body = gen.generate(config)
        import re
        assert re.search(r"## Release v1\.5\.0 \(\d{4}-\d{2}-\d{2}\)", body)


class TestInferBumpType:
    def test_major(self) -> None:
        assert infer_bump_type("2.0.0", "1.9.9") == "major"

    def test_minor(self) -> None:
        assert infer_bump_type("1.5.0", "1.4.2") == "minor"

    def test_patch(self) -> None:
        assert infer_bump_type("1.4.3", "1.4.2") == "patch"

    def test_v_prefix(self) -> None:
        assert infer_bump_type("v1.5.0", "v1.4.2") == "minor"

    def test_prerelease_stripped(self) -> None:
        assert infer_bump_type("1.4.3-rc1", "1.4.2") == "patch"

    def test_unparseable_defaults_patch(self) -> None:
        assert infer_bump_type("not-a-version", "1.0.0") == "patch"


class TestScrapeTapRefs:
    def test_single_ref(self) -> None:
        assert scrape_tap_refs("Fixed TAP-123 issue") == ["TAP-123"]

    def test_multiple_refs(self) -> None:
        refs = scrape_tap_refs("TAP-100 and TAP-200 and TAP-300")
        assert refs == ["TAP-100", "TAP-200", "TAP-300"]

    def test_deduplicates(self) -> None:
        refs = scrape_tap_refs("TAP-100 mentioned again TAP-100")
        assert refs == ["TAP-100"]

    def test_no_refs(self) -> None:
        assert scrape_tap_refs("no issue references here") == []

    def test_preserves_order(self) -> None:
        refs = scrape_tap_refs("TAP-300 then TAP-100 then TAP-200")
        assert refs == ["TAP-300", "TAP-100", "TAP-200"]
