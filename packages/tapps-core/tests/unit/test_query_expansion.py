"""Unit tests for tapps_core.experts.query_expansion."""

from __future__ import annotations

from tapps_core.experts.domain_detector import DomainDetector
from tapps_core.experts.query_expansion import (
    SYNONYMS,
    expand_keywords,
    expand_query,
)


# ---------------------------------------------------------------------------
# expand_query tests
# ---------------------------------------------------------------------------


class TestExpandQuery:
    """Tests for the expand_query function."""

    def test_synonym_appended(self) -> None:
        result = expand_query("How do I fix this vuln?")
        assert "vulnerability" in result
        # Original text preserved
        assert "vuln" in result

    def test_multi_word_synonym(self) -> None:
        result = expand_query("Set up continuous integration for my project")
        assert "ci" in result

    def test_unknown_words_passthrough(self) -> None:
        original = "How do I use foobarqux in my project?"
        result = expand_query(original)
        assert result == original

    def test_case_insensitive(self) -> None:
        result = expand_query("Is VULN present in my code?")
        assert "vulnerability" in result

    def test_canonical_already_present_not_duplicated(self) -> None:
        result = expand_query("Check for vulnerability and vuln reports")
        # "vulnerability" is already in the original, should not be appended again
        count = result.lower().count("vulnerability")
        assert count == 1

    def test_empty_question(self) -> None:
        result = expand_query("")
        assert result == ""

    def test_multiple_synonyms_expanded(self) -> None:
        result = expand_query("Check auth and perf issues")
        assert "authentication" in result
        assert "performance" in result

    def test_no_duplicate_additions(self) -> None:
        # "vulns" and "vuln" both map to "vulnerability" — only appended once
        result = expand_query("Found vulns and a vuln")
        count = result.lower().split().count("vulnerability")
        assert count == 1


# ---------------------------------------------------------------------------
# expand_keywords tests
# ---------------------------------------------------------------------------


class TestExpandKeywords:
    """Tests for the expand_keywords function."""

    def test_synonym_keyword_expanded(self) -> None:
        result = expand_keywords(["vuln", "cache"])
        assert "vulnerability" in result
        assert "vuln" in result
        assert "cache" in result

    def test_unknown_keyword_passthrough(self) -> None:
        result = expand_keywords(["unknownword"])
        assert result == ["unknownword"]

    def test_no_duplicates(self) -> None:
        result = expand_keywords(["vulnerability", "vuln"])
        assert result.count("vulnerability") == 1


# ---------------------------------------------------------------------------
# SYNONYMS dict validation
# ---------------------------------------------------------------------------


class TestSynonymsDictionary:
    """Validate the SYNONYMS dictionary structure."""

    def test_synonyms_not_empty(self) -> None:
        assert len(SYNONYMS) >= 50

    def test_all_keys_lowercase(self) -> None:
        for key in SYNONYMS:
            assert key == key.lower(), f"Key '{key}' is not lowercase"

    def test_all_values_lowercase(self) -> None:
        for key, val in SYNONYMS.items():
            assert val == val.lower(), f"Value '{val}' for key '{key}' is not lowercase"


# ---------------------------------------------------------------------------
# Domain detection improvement tests
# ---------------------------------------------------------------------------


class TestDomainDetectionWithExpansion:
    """Verify that synonym expansion improves domain detection recall."""

    def test_vuln_routes_to_security(self) -> None:
        # "vuln" is not in DOMAIN_KEYWORDS, but synonym maps it to "vulnerability"
        results = DomainDetector.detect_from_question("I found a vuln in the code")
        assert results
        domains = [r.domain for r in results]
        assert "security" in domains

    def test_perf_routes_to_performance(self) -> None:
        results = DomainDetector.detect_from_question("We need to fix perf issues")
        assert results
        domains = [r.domain for r in results]
        assert "performance-optimization" in domains

    def test_cicd_routes_to_development_workflow(self) -> None:
        results = DomainDetector.detect_from_question("How do I set up CI/CD?")
        assert results
        domains = [r.domain for r in results]
        assert "development-workflow" in domains

    def test_infra_routes_to_cloud(self) -> None:
        results = DomainDetector.detect_from_question(
            "How should I manage my infra?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "cloud-infrastructure" in domains

    def test_existing_questions_not_broken(self) -> None:
        """Expansion must not break existing well-routing questions."""
        results = DomainDetector.detect_from_question(
            "How do I prevent SQL injection?"
        )
        assert results
        assert results[0].domain == "security"
