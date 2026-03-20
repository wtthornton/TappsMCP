"""Tests for release notes generation."""

from __future__ import annotations

import pytest

from docs_mcp.generators.release_notes import ReleaseNotes, ReleaseNotesGenerator
from tests.helpers import make_commit as _commit
from tests.helpers import make_version as _version


@pytest.fixture
def generator() -> ReleaseNotesGenerator:
    return ReleaseNotesGenerator()


# ---------------------------------------------------------------------------
# ReleaseNotes model tests
# ---------------------------------------------------------------------------


class TestReleaseNotesModel:
    def test_defaults(self) -> None:
        notes = ReleaseNotes(version="1.0.0", date="2026-01-01")
        assert notes.version == "1.0.0"
        assert notes.date == "2026-01-01"
        assert notes.highlights == []
        assert notes.breaking_changes == []
        assert notes.features == []
        assert notes.fixes == []
        assert notes.other_changes == []
        assert notes.contributors == []


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


class TestReleaseNotesGeneration:
    def test_features_extracted(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.0", "2026-01-15T00:00:00+00:00", [
            _commit("feat: add user dashboard"),
            _commit("feat(api): add REST endpoints"),
        ])
        notes = generator.generate(vb)
        assert len(notes.features) == 2
        assert "add user dashboard" in notes.features[0]
        assert "**api:**" in notes.features[1]

    def test_fixes_extracted(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.1", "2026-01-20T00:00:00+00:00", [
            _commit("fix: resolve crash on login"),
            _commit("fix(db): connection timeout"),
        ])
        notes = generator.generate(vb)
        assert len(notes.fixes) == 2

    def test_breaking_changes_listed(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("2.0.0", "2026-02-01T00:00:00+00:00", [
            _commit("feat!: redesign API contract"),
        ])
        notes = generator.generate(vb)
        assert len(notes.breaking_changes) == 1
        assert "redesign API contract" in notes.breaking_changes[0]

    def test_contributors_extracted(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.0", "2026-01-15T00:00:00+00:00", [
            _commit("feat: feature A", author="Alice"),
            _commit("fix: fix B", author="Bob"),
            _commit("feat: feature C", author="Alice"),
        ])
        notes = generator.generate(vb)
        assert sorted(notes.contributors) == ["Alice", "Bob"]

    def test_highlights_from_features(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.0", "2026-01-15T00:00:00+00:00", [
            _commit("feat: dashboard"),
            _commit("feat: reports"),
        ])
        notes = generator.generate(vb)
        assert len(notes.highlights) >= 1
        assert len(notes.highlights) <= 5

    def test_highlights_prioritize_breaking(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("2.0.0", "2026-02-01T00:00:00+00:00", [
            _commit("feat!: redesign API"),
            _commit("feat: new feature"),
        ])
        notes = generator.generate(vb)
        assert notes.highlights[0].startswith("BREAKING:")

    def test_other_changes_captured(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.0", "2026-01-15T00:00:00+00:00", [
            _commit("docs: update readme"),
            _commit("refactor: clean up code"),
            _commit("chore: update deps"),
        ])
        notes = generator.generate(vb)
        assert len(notes.other_changes) == 3

    def test_empty_version(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.0", "2026-01-15T00:00:00+00:00", [])
        notes = generator.generate(vb)
        assert notes.version == "1.0.0"
        assert notes.features == []
        assert notes.fixes == []
        assert notes.breaking_changes == []
        assert notes.contributors == []

    def test_date_formatting(self, generator: ReleaseNotesGenerator) -> None:
        vb = _version("1.0.0", "2026-01-15T10:30:00+00:00", [])
        notes = generator.generate(vb)
        assert notes.date == "2026-01-15"

    def test_generate_from_versions_latest(self, generator: ReleaseNotesGenerator) -> None:
        versions = [
            _version("2.0.0", "2026-02-15T00:00:00+00:00", [
                _commit("feat: v2 feature"),
            ]),
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: v1 feature"),
            ]),
        ]
        notes = generator.generate_from_versions(versions)
        assert notes is not None
        assert notes.version == "2.0.0"

    def test_generate_from_versions_specific(self, generator: ReleaseNotesGenerator) -> None:
        versions = [
            _version("2.0.0", "2026-02-15T00:00:00+00:00", [
                _commit("feat: v2 feature"),
            ]),
            _version("1.0.0", "2026-01-01T00:00:00+00:00", [
                _commit("feat: v1 feature"),
            ]),
        ]
        notes = generator.generate_from_versions(versions, version="1.0.0")
        assert notes is not None
        assert notes.version == "1.0.0"

    def test_generate_from_versions_not_found(self, generator: ReleaseNotesGenerator) -> None:
        versions = [
            _version("1.0.0", "2026-01-01T00:00:00+00:00", []),
        ]
        notes = generator.generate_from_versions(versions, version="3.0.0")
        assert notes is None

    def test_generate_from_versions_empty(self, generator: ReleaseNotesGenerator) -> None:
        notes = generator.generate_from_versions([])
        assert notes is None


# ---------------------------------------------------------------------------
# Markdown rendering tests
# ---------------------------------------------------------------------------


class TestMarkdownRendering:
    def test_basic_rendering(self, generator: ReleaseNotesGenerator) -> None:
        notes = ReleaseNotes(
            version="1.0.0",
            date="2026-01-15",
            features=["New dashboard"],
            fixes=["Login bug fix"],
        )
        md = generator.render_markdown(notes)
        assert "# Release 1.0.0" in md
        assert "**Release Date:** 2026-01-15" in md
        assert "## New Features" in md
        assert "- New dashboard" in md
        assert "## Bug Fixes" in md
        assert "- Login bug fix" in md

    def test_highlights_rendered(self, generator: ReleaseNotesGenerator) -> None:
        notes = ReleaseNotes(
            version="1.0.0",
            date="2026-01-15",
            highlights=["Major new feature"],
        )
        md = generator.render_markdown(notes)
        assert "## Highlights" in md
        assert "- Major new feature" in md

    def test_breaking_changes_rendered(self, generator: ReleaseNotesGenerator) -> None:
        notes = ReleaseNotes(
            version="2.0.0",
            date="2026-02-01",
            breaking_changes=["API redesigned"],
        )
        md = generator.render_markdown(notes)
        assert "## Breaking Changes" in md
        assert "- API redesigned" in md

    def test_contributors_rendered(self, generator: ReleaseNotesGenerator) -> None:
        notes = ReleaseNotes(
            version="1.0.0",
            date="2026-01-15",
            contributors=["Alice", "Bob"],
        )
        md = generator.render_markdown(notes)
        assert "## Contributors" in md
        assert "- Alice" in md
        assert "- Bob" in md

    def test_empty_sections_omitted(self, generator: ReleaseNotesGenerator) -> None:
        notes = ReleaseNotes(
            version="1.0.0",
            date="2026-01-15",
        )
        md = generator.render_markdown(notes)
        assert "## New Features" not in md
        assert "## Bug Fixes" not in md
        assert "## Breaking Changes" not in md
        assert "## Other Changes" not in md
        assert "## Contributors" not in md

    def test_other_changes_rendered(self, generator: ReleaseNotesGenerator) -> None:
        notes = ReleaseNotes(
            version="1.0.0",
            date="2026-01-15",
            other_changes=["Update docs", "Refactor code"],
        )
        md = generator.render_markdown(notes)
        assert "## Other Changes" in md
        assert "- Update docs" in md
        assert "- Refactor code" in md


# ---------------------------------------------------------------------------
# Highlight extraction tests
# ---------------------------------------------------------------------------


class TestHighlightExtraction:
    def test_max_five_highlights(self, generator: ReleaseNotesGenerator) -> None:
        features = [f"feature {i}" for i in range(10)]
        highlights = generator._extract_highlights(features, [])
        assert len(highlights) == 5

    def test_breaking_first(self, generator: ReleaseNotesGenerator) -> None:
        breaking = ["API change"]
        features = ["new feature"]
        highlights = generator._extract_highlights(features, breaking)
        assert highlights[0] == "BREAKING: API change"
        assert highlights[1] == "new feature"

    def test_empty_inputs(self, generator: ReleaseNotesGenerator) -> None:
        highlights = generator._extract_highlights([], [])
        assert highlights == []
