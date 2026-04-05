"""Failure pattern analysis for benchmark results.

Identifies instances that failed with TAPPS context but succeeded
without it or with human context, clusters failures by patterns,
and generates template improvement suggestions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from tapps_mcp.benchmark.models import BenchmarkInstance, BenchmarkResult

__all__ = [
    "FailureAnalyzer",
    "FailurePattern",
    "TemplateSuggestion",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum number of suggested fixes per analysis.
_MAX_SUGGESTIONS = 5

# Maximum example instance IDs to include per pattern.
_MAX_EXAMPLES = 5

# Common error keywords to cluster by.
_ERROR_KEYWORDS = (
    "timeout",
    "import",
    "syntax",
    "assertion",
    "type",
    "attribute",
    "permission",
    "memory",
    "connection",
    "configuration",
    "dependency",
    "version",
    "path",
    "encoding",
    "key",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class FailurePattern(BaseModel):
    """A recurring failure pattern identified across benchmark results."""

    model_config = ConfigDict(frozen=True)

    pattern_type: str = Field(
        description="Type of failure pattern (e.g., 'timeout', 'import_error')."
    )
    frequency: int = Field(ge=0, description="Number of times this pattern occurred.")
    affected_repos: list[str] = Field(
        default_factory=list,
        description="Repositories affected by this pattern.",
    )
    example_instance_ids: list[str] = Field(
        default_factory=list,
        description="Example instance IDs exhibiting this pattern.",
    )
    suggested_fix: str = Field(description="Suggested template fix for this pattern.")


class TemplateSuggestion(BaseModel):
    """A specific suggestion for improving the template."""

    model_config = ConfigDict(frozen=True)

    section: str = Field(description="Template section to modify.")
    action: str = Field(description="Action: 'add', 'modify', or 'remove'.")
    content: str = Field(description="Content to add or modify.")
    rationale: str = Field(description="Reason for this suggestion.")
    expected_impact: str = Field(description="Expected impact on resolution rate.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_repo(instance_id: str) -> str:
    """Extract repository name from an instance_id.

    Supports ``org__repo__number`` and ``org/repo-number`` formats.
    """
    parts = instance_id.split("__")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"

    if "/" in instance_id:
        slash_idx = instance_id.index("/")
        after_slash = instance_id[slash_idx + 1 :]
        last_hyphen = after_slash.rfind("-")
        if last_hyphen >= 0:
            return f"{instance_id[:slash_idx]}/{after_slash[:last_hyphen]}"
        return instance_id

    return "unknown"


def _classify_error(error: str | None) -> str:
    """Classify an error message into a pattern type.

    Scans the error string for known keywords using word-boundary
    matching and returns the first match. Falls back to ``"unknown"``
    when no keyword matches.
    """
    if not error:
        return "no_error_message"

    lower_error = error.lower()
    for keyword in _ERROR_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}", lower_error):
            return keyword

    return "unknown"


def _build_fix_suggestion(pattern_type: str) -> str:
    """Generate a suggested fix based on the pattern type."""
    suggestions: dict[str, str] = {
        "timeout": (
            "Add guidance about time-sensitive operations and "
            "suggest breaking complex tasks into smaller steps."
        ),
        "import": (
            "Add a section listing common import patterns and "
            "dependency resolution strategies for the affected repos."
        ),
        "syntax": (
            "Include language-specific syntax guidelines and common pitfalls in the template."
        ),
        "assertion": (
            "Add testing strategy guidance with emphasis on assertion patterns and test structure."
        ),
        "type": (
            "Include type system guidance relevant to the "
            "affected repositories' language/framework."
        ),
        "attribute": (
            "Add API reference hints for commonly misused attributes in the affected codebase."
        ),
        "permission": ("Include filesystem and permission handling guidelines in the template."),
        "memory": ("Add memory management best practices and resource cleanup patterns."),
        "connection": ("Include network and connection handling guidance with retry strategies."),
        "configuration": (
            "Add configuration management patterns and environment variable documentation."
        ),
        "dependency": ("Include dependency resolution and version management guidance."),
        "version": ("Add version compatibility notes and migration guidelines."),
        "path": ("Include cross-platform path handling guidance and common path-related pitfalls."),
        "encoding": ("Add encoding handling guidelines, especially for file I/O operations."),
        "key": ("Include key/secret management patterns and configuration lookup guidance."),
        "no_error_message": (
            "Improve error reporting in the evaluation pipeline to capture failure details."
        ),
    }
    return suggestions.get(
        pattern_type,
        "Review the failure instances and add targeted guidance to address the recurring issue.",
    )


def _split_template_sections(template: str) -> list[str]:
    """Extract section names from a markdown template."""
    return [line.lstrip("#").strip() for line in template.split("\n") if line.startswith("## ")]


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class FailureAnalyzer:
    """Analyze failure patterns in benchmark results."""

    def analyze_failures(
        self,
        results: list[BenchmarkResult],
        instances: list[BenchmarkInstance],
    ) -> list[FailurePattern]:
        """Identify recurring failure patterns.

        Finds instances that failed (not resolved) and clusters them
        by error patterns and repositories. Generates suggested fixes
        for each pattern (capped at ``_MAX_SUGGESTIONS``).

        Args:
            results: Benchmark results to analyze.
            instances: Benchmark instances for context.

        Returns:
            List of failure patterns sorted by frequency (descending).
        """
        # Find failed results
        failed = [r for r in results if not r.resolved]
        if not failed:
            logger.info("no_failures_found", total_results=len(results))
            return []

        # Cluster by error pattern
        pattern_instances: dict[str, list[BenchmarkResult]] = defaultdict(list)
        for result in failed:
            pattern_type = _classify_error(result.error)
            pattern_instances[pattern_type].append(result)

        # Build failure patterns
        patterns: list[FailurePattern] = []
        for pattern_type, pattern_results in sorted(
            pattern_instances.items(), key=lambda x: -len(x[1])
        ):
            repos: set[str] = set()
            example_ids: list[str] = []

            for result in pattern_results:
                repo = _extract_repo(result.instance_id)
                repos.add(repo)
                if len(example_ids) < _MAX_EXAMPLES:
                    example_ids.append(result.instance_id)

            pattern = FailurePattern(
                pattern_type=pattern_type,
                frequency=len(pattern_results),
                affected_repos=sorted(repos),
                example_instance_ids=example_ids,
                suggested_fix=_build_fix_suggestion(pattern_type),
            )
            patterns.append(pattern)

        # Cap at max suggestions
        patterns = patterns[:_MAX_SUGGESTIONS]

        logger.info(
            "failure_analysis_complete",
            total_failed=len(failed),
            patterns_found=len(patterns),
            total_results=len(results),
        )

        return patterns

    def generate_suggestions(
        self,
        patterns: list[FailurePattern],
        template: str,
    ) -> list[TemplateSuggestion]:
        """Generate template improvement suggestions from failure patterns.

        Maps failure patterns to specific template sections that should
        be added or modified.

        Args:
            patterns: Failure patterns from ``analyze_failures``.
            template: Current template content.

        Returns:
            List of template suggestions.
        """
        existing_sections = _split_template_sections(template)
        existing_lower = {s.lower() for s in existing_sections}
        suggestions: list[TemplateSuggestion] = []

        for pattern in patterns:
            section_name = _pattern_to_section(pattern.pattern_type)

            # Determine action based on whether section exists
            if section_name.lower() in existing_lower:
                action = "modify"
                rationale = (
                    f"The '{section_name}' section exists but does not "
                    f"adequately address {pattern.pattern_type} failures "
                    f"({pattern.frequency} occurrences across "
                    f"{len(pattern.affected_repos)} repos)."
                )
                expected_impact = (
                    f"May resolve up to {pattern.frequency} currently-failing instances."
                )
            else:
                action = "add"
                rationale = (
                    f"No section addresses {pattern.pattern_type} failures. "
                    f"Adding guidance could help with "
                    f"{pattern.frequency} failing instances."
                )
                expected_impact = (
                    f"Could improve resolution by addressing "
                    f"{pattern.frequency} failure instances "
                    f"across {len(pattern.affected_repos)} repositories."
                )

            suggestion = TemplateSuggestion(
                section=section_name,
                action=action,
                content=pattern.suggested_fix,
                rationale=rationale,
                expected_impact=expected_impact,
            )
            suggestions.append(suggestion)

        logger.debug(
            "suggestions_generated",
            count=len(suggestions),
        )

        return suggestions[:_MAX_SUGGESTIONS]


def _pattern_to_section(pattern_type: str) -> str:
    """Map a failure pattern type to a template section name."""
    section_map: dict[str, str] = {
        "timeout": "Performance Guidelines",
        "import": "Dependency Management",
        "syntax": "Code Style Guidelines",
        "assertion": "Testing Strategy",
        "type": "Type System Guidelines",
        "attribute": "API Reference",
        "permission": "Security & Permissions",
        "memory": "Resource Management",
        "connection": "Network & Connectivity",
        "configuration": "Configuration Management",
        "dependency": "Dependency Management",
        "version": "Version Compatibility",
        "path": "File System Operations",
        "encoding": "Text Encoding",
        "key": "Configuration Management",
        "no_error_message": "Error Handling",
    }
    return section_map.get(pattern_type, "General Guidelines")
