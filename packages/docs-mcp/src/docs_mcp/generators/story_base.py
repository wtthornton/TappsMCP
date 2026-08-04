"""Shared constants and helpers for the story generator mixins.

``StoryGeneratorBase`` owns the class-level configuration and the three
helpers the section mixins call across group boundaries — task
suggestion, slugification, and test-name derivation. Split out of
``stories.py`` under TAP-5609; each mixin inherits from it so those
cross-group calls stay statically resolvable.
"""

from __future__ import annotations

import re
from typing import ClassVar

from docs_mcp.generators.story_models import StoryConfig, StoryTask


class StoryGeneratorBase:
    """Class-level configuration and cross-group helpers."""

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({"standard", "comprehensive"})
    VALID_SIZES: ClassVar[frozenset[str]] = frozenset({"S", "M", "L", "XL", ""})
    VALID_CRITERIA_FORMATS: ClassVar[frozenset[str]] = frozenset({"checkbox", "gherkin"})
    VALID_AUDIENCES: ClassVar[frozenset[str]] = frozenset({"agent", "human"})
    VALID_ISSUE_KINDS: ClassVar[frozenset[str]] = frozenset(
        {"implementable", "decision", "map-parent"}
    )

    _AGENT_TITLE_MAX: ClassVar[int] = 80
    _AGENT_FILE_ANCHOR_RE: ClassVar[re.Pattern[str]] = re.compile(r"[\w./\\-]+\.\w+:\d+(?:-\d+)?")
    _TAP_REF_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bTAP-\d+\b")

    _STOPWORDS: ClassVar[frozenset[str]] = frozenset(
        {
            "the",
            "and",
            "is",
            "are",
            "should",
            "that",
            "when",
            "then",
            "given",
            "a",
            "an",
            "of",
            "in",
            "to",
            "for",
            "with",
            "be",
            "has",
            "have",
            "it",
            "its",
        }
    )

    _MAX_TEST_NAME_LEN: ClassVar[int] = 80

    # Keyword-to-task patterns for the task suggestion engine (Story 92.4).
    # Multiple keywords that share the same list object are deduplicated via id().
    # First matching keyword group wins.
    _model_tasks: ClassVar[list[str]] = [
        "Define data model fields and relationships",
        "Write migration script",
        "Add model validation",
    ]
    _api_tasks: ClassVar[list[str]] = [
        "Define request/response schema",
        "Implement endpoint handler",
        "Add input validation",
        "Add error responses",
    ]
    _test_tasks: ClassVar[list[str]] = [
        "Write unit tests for happy path",
        "Write edge case tests",
        "Add integration test",
    ]
    _ui_tasks: ClassVar[list[str]] = [
        "Create component scaffold",
        "Add form validation",
        "Add styling/CSS",
        "Add accessibility attributes",
    ]
    _validation_tasks: ClassVar[list[str]] = [
        "Define validation rules",
        "Implement validation logic",
        "Add validation error messages",
    ]
    _auth_tasks: ClassVar[list[str]] = [
        "Implement auth flow",
        "Add token generation/validation",
        "Add session management",
    ]
    _TASK_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "model": _model_tasks,
        "schema": _model_tasks,
        "database": _model_tasks,
        "endpoint": _api_tasks,
        "api": _api_tasks,
        "route": _api_tasks,
        "test": _test_tasks,
        "coverage": _test_tasks,
        "ui": _ui_tasks,
        "component": _ui_tasks,
        "form": _ui_tasks,
        "validate": _validation_tasks,
        "validation": _validation_tasks,
        "auth": _auth_tasks,
        "login": _auth_tasks,
        "token": _auth_tasks,
    }

    @classmethod
    def _suggest_tasks(cls, config: StoryConfig) -> list[StoryTask]:
        """Suggest implementation tasks from title/description keywords.

        Scans the title and description for known keyword patterns and returns
        a deduplicated list of relevant task stubs. Falls back to a generic
        3-task pattern when no keywords match but title is non-empty. Returns
        an empty list when the title is empty/whitespace (preserve existing
        "Define implementation tasks..." placeholder).

        When ``config.files`` is provided, the first file path is associated
        with the first task stub.

        Returns:
            A list of :class:`StoryTask` with inferred descriptions.
        """
        title = config.title.strip()
        if not title:
            return []

        combined = (title + " " + (config.description or "")).lower()
        tokens = set(re.split(r"[\s\-_/]+", combined))

        task_descriptions: list[str] = []
        seen_patterns: set[int] = set()

        for keyword, task_list in cls._TASK_PATTERNS.items():
            pattern_id = id(task_list)
            if pattern_id in seen_patterns:
                continue
            if keyword in tokens or keyword in combined:
                seen_patterns.add(pattern_id)
                task_descriptions = task_list
                break  # First matching keyword group wins

        if not task_descriptions:
            # Generic fallback: title-derived implementation task
            task_descriptions = [
                f"Implement {title.lower()}",
                "Write unit tests",
                "Update documentation",
            ]

        # Associate first file path with the first task when files are provided.
        first_file = config.files[0] if config.files else ""
        tasks: list[StoryTask] = []
        for i, description in enumerate(task_descriptions):
            file_path = first_file if i == 0 and first_file else ""
            tasks.append(StoryTask(description=description, file_path=file_path))

        return tasks

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a URL-friendly slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")

    @classmethod
    def generate_test_name(cls, criterion: str, *, index: int = 0) -> str:
        """Generate a valid Python test function name from an acceptance criterion.

        The result follows the pattern ``test_<verb>_<noun>_<qualifier>``
        (or ``test_ac<N>_<verb>_<noun>_<qualifier>`` when *index* > 0).
        It is guaranteed to:

        * be at most 80 characters,
        * never truncate mid-word,
        * be a valid Python identifier (``test_`` prefix, only ``[a-z0-9_]``),
        * have common stopwords removed.

        Args:
            criterion: Acceptance criterion text (e.g. "Validation rejects
                empty fields when the form is submitted").
            index: 1-based AC number.  When > 0, the name is prefixed with
                ``ac<index>_`` (e.g. ``test_ac1_validation_rejects``).

        Returns:
            A clean test function name such as ``test_validation_rejects_empty_fields``.
        """
        if not criterion or not criterion.strip():
            if index > 0:
                return f"test_ac{index}_story_acceptance"
            return "test_story_acceptance"

        # Lowercase and strip non-alphanumeric (keep spaces for splitting).
        text = criterion.lower().strip()
        text = re.sub(r"[^a-z0-9\s]", "", text)

        # Split into words, remove stopwords.
        words = [w for w in text.split() if w and w not in cls._STOPWORDS]

        if not words:
            if index > 0:
                return f"test_ac{index}_story_acceptance"
            return "test_story_acceptance"

        # Build prefix.
        prefix = f"test_ac{index}_" if index > 0 else "test_"

        # Assemble words into the name, respecting max length.
        parts: list[str] = []
        current_len = len(prefix)
        for word in words:
            # +1 for the underscore separator between words.
            needed = len(word) + (1 if parts else 0)
            if current_len + needed > cls._MAX_TEST_NAME_LEN:
                break
            parts.append(word)
            current_len += needed

        if not parts:
            # First word alone exceeds limit -- take it truncated to fit.
            available = cls._MAX_TEST_NAME_LEN - len(prefix)
            if available > 0:
                parts.append(words[0][:available])
            else:
                return prefix.rstrip("_")

        name = prefix + "_".join(parts)

        # Final safety: ensure valid Python identifier.
        if not name.isidentifier():
            name = re.sub(r"[^a-z0-9_]", "", name)
            if not name.startswith("test_"):
                name = "test_" + name

        return name
