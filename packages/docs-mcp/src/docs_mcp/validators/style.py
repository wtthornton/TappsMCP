"""Documentation style and tone validation engine.

Provides deterministic, regex/pattern-based style checking for markdown
documentation.  Each rule receives parsed content and returns issues with
severity, location, and fix suggestions.

Epic 84 -- Doc Style & Tone Validation.
"""

from __future__ import annotations

import contextlib
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Literal

if TYPE_CHECKING:
    from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from docs_mcp.constants import SKIP_DIRS as _BASE_SKIP_DIRS

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]

_MAX_FILES = 200

Severity = Literal["error", "warning", "suggestion"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class StyleIssue(BaseModel):
    """A single style issue found in a document."""

    rule: str
    severity: Severity
    line: int
    column: int = 0
    message: str
    suggestion: str = ""
    context: str = ""


class FileStyleResult(BaseModel):
    """Style check results for a single file."""

    file_path: str
    issues: list[StyleIssue] = Field(default_factory=list)
    score: float = 100.0


class StyleReport(BaseModel):
    """Aggregated style check results across files."""

    total_files: int = 0
    total_issues: int = 0
    files: list[FileStyleResult] = Field(default_factory=list)
    aggregate_score: float = 100.0
    issue_counts: dict[str, int] = Field(default_factory=dict)
    top_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class StyleConfig(BaseModel):
    """Configuration for the style checker."""

    enabled_rules: list[str] = Field(
        default_factory=lambda: [
            "passive_voice",
            "jargon",
            "sentence_length",
            "heading_consistency",
            "tense_consistency",
        ],
    )
    max_sentence_words: int = 40
    heading_style: Literal["sentence", "title"] = "sentence"
    custom_terms: list[str] = Field(default_factory=list)
    jargon_terms: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule base
# ---------------------------------------------------------------------------


class RuleBase(ABC):
    """Abstract base class for style rules."""

    name: str = ""
    description: str = ""
    default_severity: Severity = "warning"

    @abstractmethod
    def check(self, content: str, config: StyleConfig) -> list[StyleIssue]:
        """Check content and return any style issues found."""


# ---------------------------------------------------------------------------
# Passive Voice Rule
# ---------------------------------------------------------------------------

# Common past participles for passive voice detection.
_PAST_PARTICIPLES: frozenset[str] = frozenset({
    "accepted", "accomplished", "achieved", "acquired", "added", "adjusted",
    "allowed", "applied", "approved", "assigned", "authorized", "avoided",
    "based", "been", "broken", "built", "called", "caused", "changed",
    "chosen", "closed", "collected", "combined", "completed", "composed",
    "configured", "connected", "considered", "consumed", "contained",
    "converted", "copied", "corrected", "covered", "created", "customized",
    "defined", "deleted", "delivered", "deployed", "described", "designed",
    "detected", "determined", "developed", "disabled", "displayed",
    "distributed", "documented", "done", "downloaded", "driven",
    "enabled", "enforced", "established", "evaluated", "examined",
    "exceeded", "excluded", "executed", "expected", "exported", "expressed",
    "extended", "extracted",
    "failed", "fixed", "followed", "formatted", "found", "frozen",
    "generated", "given", "granted",
    "handled", "held", "hidden",
    "identified", "ignored", "implemented", "imported", "improved",
    "included", "increased", "indicated", "initialized", "injected",
    "installed", "integrated", "intended", "introduced", "invalidated",
    "invoked",
    "kept", "known",
    "launched", "left", "limited", "linked", "listed", "loaded", "located",
    "logged", "lost",
    "made", "maintained", "managed", "mapped", "marked", "measured",
    "merged", "migrated", "modified", "monitored", "moved",
    "named", "needed", "noted",
    "observed", "obtained", "offered", "omitted", "opened", "optimized",
    "organized", "overridden", "owned",
    "parsed", "passed", "performed", "permitted", "placed", "planned",
    "populated", "preferred", "prepared", "presented", "prevented",
    "processed", "produced", "prohibited", "protected", "provided",
    "published",
    "raised", "reached", "read", "received", "recognized", "recommended",
    "recorded", "reduced", "referenced", "registered", "rejected",
    "released", "removed", "renamed", "replaced", "reported", "represented",
    "requested", "required", "reserved", "reset", "resolved", "restricted",
    "retained", "retrieved", "returned", "reviewed", "revoked", "run",
    "saved", "scanned", "scheduled", "secured", "seen", "selected", "sent",
    "separated", "served", "set", "shared", "shown", "signed", "skipped",
    "sorted", "specified", "split", "started", "stopped", "stored",
    "submitted", "supported", "suppressed",
    "taken", "tested", "thrown", "tracked", "transferred", "transformed",
    "triggered", "truncated", "turned", "typed",
    "updated", "uploaded", "used", "utilized",
    "validated", "verified", "viewed", "violated",
    "warned", "written",
})

_BE_VERBS = r"\b(?:is|are|was|were|be|been|being)\b"
_PASSIVE_RE = re.compile(
    rf"({_BE_VERBS})\s+(\w+ed|\w+en|\w+wn|\w+nt|\w+pt|\w+lt)\b",
    re.IGNORECASE,
)


class PassiveVoiceRule(RuleBase):
    """Detect passive voice constructions."""

    name = "passive_voice"
    description = "Flags passive voice (be-verb + past participle)."
    default_severity: Severity = "suggestion"

    def check(self, content: str, config: StyleConfig) -> list[StyleIssue]:
        issues: list[StyleIssue] = []
        for line_num, line in enumerate(_content_lines(content), start=1):
            if _is_code_or_frontmatter(line):
                continue
            for match in _PASSIVE_RE.finditer(line):
                participle = match.group(2).lower()
                if participle in _PAST_PARTICIPLES:
                    issues.append(StyleIssue(
                        rule=self.name,
                        severity=self.default_severity,
                        line=line_num,
                        column=match.start() + 1,
                        message=f"Passive voice: '{match.group(0).strip()}'.",
                        suggestion="Consider rewriting in active voice.",
                        context=line.strip()[:120],
                    ))
        return issues


# ---------------------------------------------------------------------------
# Jargon Rule
# ---------------------------------------------------------------------------

_DEFAULT_JARGON: list[str] = [
    "utilize", "utilise", "leverage", "synergy", "synergize",
    "paradigm", "holistic", "proactive", "proactively",
    "actionable", "scalable", "robust",
    "bleeding edge", "cutting edge", "best of breed",
    "circle back", "deep dive", "move the needle",
    "low-hanging fruit", "boil the ocean",
    "at the end of the day", "going forward",
    "touch base", "drill down",
]


class JargonRule(RuleBase):
    """Flag jargon and buzzwords."""

    name = "jargon"
    description = "Flags jargon, buzzwords, and corporate-speak."
    default_severity: Severity = "warning"

    def check(self, content: str, config: StyleConfig) -> list[StyleIssue]:
        issues: list[StyleIssue] = []
        terms = config.jargon_terms if config.jargon_terms else _DEFAULT_JARGON
        custom_lower = {t.lower() for t in config.custom_terms}

        patterns: list[tuple[str, re.Pattern[str]]] = []
        for term in terms:
            if term.lower() in custom_lower:
                continue
            patterns.append((term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)))

        for line_num, line in enumerate(_content_lines(content), start=1):
            if _is_code_or_frontmatter(line):
                continue
            for term, pat in patterns:
                for match in pat.finditer(line):
                    issues.append(StyleIssue(
                        rule=self.name,
                        severity=self.default_severity,
                        line=line_num,
                        column=match.start() + 1,
                        message=f"Jargon: '{match.group(0)}'.",
                        suggestion=f"Replace '{term}' with a simpler alternative.",
                        context=line.strip()[:120],
                    ))
        return issues


# ---------------------------------------------------------------------------
# Sentence Length Rule
# ---------------------------------------------------------------------------

_SENTENCE_END_RE = re.compile(r"[.!?]+(?:\s|$)")


class SentenceLengthRule(RuleBase):
    """Flag overly long sentences."""

    name = "sentence_length"
    description = "Flags sentences exceeding the configured word limit."
    default_severity: Severity = "warning"

    def check(self, content: str, config: StyleConfig) -> list[StyleIssue]:
        issues: list[StyleIssue] = []
        max_words = config.max_sentence_words

        for line_num, line in enumerate(_content_lines(content), start=1):
            if _is_code_or_frontmatter(line):
                continue
            if line.startswith("#") or line.startswith("|"):
                continue

            sentences = _SENTENCE_END_RE.split(line)
            for sentence in sentences:
                words = sentence.split()
                if len(words) > max_words:
                    issues.append(StyleIssue(
                        rule=self.name,
                        severity=self.default_severity,
                        line=line_num,
                        column=1,
                        message=(
                            f"Sentence has {len(words)} words "
                            f"(max {max_words})."
                        ),
                        suggestion="Break into shorter sentences for clarity.",
                        context=sentence.strip()[:120],
                    ))
        return issues


# ---------------------------------------------------------------------------
# Heading Consistency Rule
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# Words that stay lowercase in title case (common articles/prepositions).
_TITLE_CASE_EXCEPTIONS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "but", "or", "nor", "for", "yet", "so",
    "at", "by", "in", "of", "on", "to", "up", "as", "is", "it",
    "vs", "via",
})


class HeadingConsistencyRule(RuleBase):
    """Check heading case style consistency."""

    name = "heading_consistency"
    description = "Flags headings that do not match the configured case style."
    default_severity: Severity = "warning"

    def check(self, content: str, config: StyleConfig) -> list[StyleIssue]:
        issues: list[StyleIssue] = []
        style = config.heading_style

        for line_num, line in enumerate(_content_lines(content), start=1):
            m = _HEADING_RE.match(line)
            if not m:
                continue
            heading_text = m.group(2).strip()
            if not heading_text:
                continue

            # Skip headings that are all-caps (acronyms, etc.)
            if heading_text.isupper():
                continue

            # Strip trailing punctuation for analysis
            cleaned = re.sub(r"[:.!?]+$", "", heading_text).strip()
            if not cleaned:
                continue

            if style == "sentence":
                if not _is_sentence_case(cleaned, config.custom_terms):
                    issues.append(StyleIssue(
                        rule=self.name,
                        severity=self.default_severity,
                        line=line_num,
                        column=len(m.group(1)) + 2,
                        message=(
                            f"Heading '{heading_text}' is not sentence case."
                        ),
                        suggestion=(
                            "Use sentence case: capitalize only the first word "
                            "and proper nouns."
                        ),
                        context=line.strip(),
                    ))
            elif style == "title" and not _is_title_case(cleaned, config.custom_terms):
                issues.append(StyleIssue(
                    rule=self.name,
                    severity=self.default_severity,
                    line=line_num,
                    column=len(m.group(1)) + 2,
                    message=(
                        f"Heading '{heading_text}' is not title case."
                    ),
                    suggestion=(
                        "Use title case: capitalize major words."
                    ),
                    context=line.strip(),
                ))
        return issues


# ---------------------------------------------------------------------------
# Tense Consistency Rule
# ---------------------------------------------------------------------------

# Imperative markers: common imperative verbs at the start of sentences/items.
_IMPERATIVE_STARTERS: frozenset[str] = frozenset({
    "add", "apply", "build", "call", "check", "choose", "clone",
    "configure", "copy", "create", "define", "delete", "deploy",
    "disable", "do", "download", "edit", "enable", "ensure",
    "enter", "execute", "export", "extend", "find", "follow",
    "generate", "get", "go", "import", "include", "initialize",
    "insert", "install", "keep", "launch", "list", "load", "look",
    "make", "merge", "modify", "move", "navigate", "note", "open",
    "pass", "perform", "place", "press", "provide", "pull", "push",
    "put", "read", "remove", "rename", "replace", "restart", "return",
    "review", "run", "save", "search", "see", "select", "send", "set",
    "specify", "start", "stop", "submit", "test", "try", "type",
    "update", "upgrade", "upload", "use", "verify", "view", "visit",
    "wait", "write",
})

# Declarative/descriptive markers.
_DECLARATIVE_RE = re.compile(
    r"^(?:this|the|it|you|we|they|he|she|each|every|any|all|when|if|once)\b",
    re.IGNORECASE,
)


class TenseConsistencyRule(RuleBase):
    """Check for mixed imperative/declarative tense in instructional content."""

    name = "tense_consistency"
    description = "Flags mixed imperative and declarative tense."
    default_severity: Severity = "suggestion"

    # Minimum lines required before flagging inconsistency
    _MIN_LINES: ClassVar[int] = 5

    def check(self, content: str, config: StyleConfig) -> list[StyleIssue]:
        issues: list[StyleIssue] = []
        imperative_lines: list[int] = []
        declarative_lines: list[int] = []

        for line_num, line in enumerate(_content_lines(content), start=1):
            if _is_code_or_frontmatter(line):
                continue
            if line.startswith("#") or line.startswith("|"):
                continue

            stripped = re.sub(r"^[-\s*>0-9.)]+", "", line).strip()
            if not stripped:
                continue

            first_word = stripped.split()[0].lower().rstrip(".,;:!?")

            if first_word in _IMPERATIVE_STARTERS:
                imperative_lines.append(line_num)
            elif _DECLARATIVE_RE.match(stripped):
                declarative_lines.append(line_num)

        total = len(imperative_lines) + len(declarative_lines)
        if total < self._MIN_LINES:
            return issues

        # Flag the minority tense as inconsistent
        if imperative_lines and declarative_lines:
            minority_is_imperative = len(imperative_lines) < len(declarative_lines)
            if minority_is_imperative:
                dominant = "declarative"
                minority_lines = imperative_lines
            else:
                dominant = "imperative"
                minority_lines = declarative_lines

            # Only flag up to 5 lines
            for line_num in minority_lines[:5]:
                issues.append(StyleIssue(
                    rule=self.name,
                    severity=self.default_severity,
                    line=line_num,
                    column=1,
                    message=(
                        f"Tense inconsistency: document is primarily "
                        f"{dominant} but this line uses "
                        f"{'imperative' if minority_is_imperative else 'declarative'}."
                    ),
                    suggestion=(
                        f"Use {dominant} tense consistently throughout."
                    ),
                ))
        return issues


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_RULE_REGISTRY: dict[str, type[RuleBase]] = {
    "passive_voice": PassiveVoiceRule,
    "jargon": JargonRule,
    "sentence_length": SentenceLengthRule,
    "heading_consistency": HeadingConsistencyRule,
    "tense_consistency": TenseConsistencyRule,
}


# ---------------------------------------------------------------------------
# Style Checker
# ---------------------------------------------------------------------------

_SKIP_DIRS: frozenset[str] = _BASE_SKIP_DIRS | frozenset({".hg", ".svn", ".env"})


class StyleChecker:
    """Deterministic documentation style and tone checker.

    Applies a configurable set of rules to markdown content and produces
    structured issue reports with per-file and aggregate scores.
    """

    def __init__(self, config: StyleConfig | None = None) -> None:
        self._config = config or StyleConfig()
        self._rules: list[RuleBase] = []
        for rule_name in self._config.enabled_rules:
            rule_cls = _RULE_REGISTRY.get(rule_name)
            if rule_cls is not None:
                self._rules.append(rule_cls())

    @property
    def config(self) -> StyleConfig:
        """Return the active configuration."""
        return self._config

    @property
    def rules(self) -> list[RuleBase]:
        """Return the list of active rules."""
        return list(self._rules)

    def check_content(
        self,
        content: str,
        *,
        file_path: str = "<string>",
    ) -> FileStyleResult:
        """Check a single piece of content for style issues."""
        all_issues: list[StyleIssue] = []
        for rule in self._rules:
            try:
                all_issues.extend(rule.check(content, self._config))
            except Exception:
                logger.debug("style_rule_failed", rule=rule.name, file=file_path)

        # Sort by line number, then column
        all_issues.sort(key=lambda i: (i.line, i.column))

        score = _calculate_file_score(all_issues)
        return FileStyleResult(
            file_path=file_path,
            issues=all_issues,
            score=score,
        )

    def check_file(self, file_path: Path, *, relative_to: Path | None = None) -> FileStyleResult:
        """Check a single file for style issues."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            logger.debug("style_read_failed", file=str(file_path))
            rel = str(file_path)
            if relative_to:
                with contextlib.suppress(ValueError):
                    rel = str(file_path.relative_to(relative_to)).replace("\\", "/")
            return FileStyleResult(file_path=rel, score=100.0)

        rel = str(file_path)
        if relative_to:
            with contextlib.suppress(ValueError):
                rel = str(file_path.relative_to(relative_to)).replace("\\", "/")

        return self.check_content(content, file_path=rel)

    def check_project(
        self,
        project_root: Path,
        *,
        doc_dirs: list[str] | None = None,
    ) -> StyleReport:
        """Check all markdown files in a project."""
        project_root = project_root.resolve()
        md_files = self._find_markdown_files(project_root, doc_dirs)

        if not md_files:
            return StyleReport(
                total_files=0,
                total_issues=0,
                aggregate_score=100.0,
            )

        results: list[FileStyleResult] = []
        for md_file in md_files[:_MAX_FILES]:
            result = self.check_file(md_file, relative_to=project_root)
            results.append(result)

        total_issues = sum(len(r.issues) for r in results)
        aggregate_score = (
            sum(r.score for r in results) / len(results) if results else 100.0
        )

        # Count issues by rule
        issue_counts: dict[str, int] = {}
        for r in results:
            for issue in r.issues:
                issue_counts[issue.rule] = issue_counts.get(issue.rule, 0) + 1

        # Top issues (most common first)
        sorted_rules = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        top_issues = [f"{name}: {count}" for name, count in sorted_rules[:5]]

        return StyleReport(
            total_files=len(results),
            total_issues=total_issues,
            files=results,
            aggregate_score=round(aggregate_score, 1),
            issue_counts=issue_counts,
            top_issues=top_issues,
        )

    def _find_markdown_files(
        self,
        project_root: Path,
        doc_dirs: list[str] | None,
    ) -> list[Path]:
        """Find all markdown files to check."""
        files: list[Path] = []

        # Root-level markdown files
        if project_root.is_dir():
            for f in sorted(project_root.iterdir()):
                if f.is_file() and f.suffix.lower() in (".md", ".mdx"):
                    name_lower = f.name.lower()
                    if name_lower not in ("license.md",):
                        files.append(f)

        # Documentation directories
        scan_dirs = doc_dirs or ["docs", "doc", "documentation"]
        for dir_name in scan_dirs:
            doc_dir = project_root / dir_name
            if doc_dir.is_dir():
                for f in sorted(doc_dir.rglob("*.md")):
                    if not any(p in _SKIP_DIRS for p in f.parts):
                        files.append(f)
                for f in sorted(doc_dir.rglob("*.mdx")):
                    if not any(p in _SKIP_DIRS for p in f.parts):
                        files.append(f)

        return files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_lines(content: str) -> list[str]:
    """Split content into lines, filtering out code blocks and frontmatter."""
    lines = content.split("\n")
    result: list[str] = []
    in_code_block = False
    in_frontmatter = False

    for i, line in enumerate(lines):
        # Frontmatter detection (only at start)
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            result.append("")
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            result.append("")
            continue

        # Code block detection
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            result.append("")
            continue
        if in_code_block:
            result.append("")
            continue

        result.append(line)

    return result


def _is_code_or_frontmatter(line: str) -> bool:
    """Quick check if a line looks like inline code or is empty."""
    stripped = line.strip()
    if not stripped:
        return True
    # Lines that are entirely inline code
    return stripped.startswith("`") and stripped.endswith("`")


def _is_sentence_case(text: str, custom_terms: list[str]) -> bool:
    """Check if text follows sentence case (first word capitalized, rest lowercase).

    Allows custom terms and known acronyms/abbreviations to be uppercase.
    """
    words = text.split()
    if not words:
        return True

    custom_set = {t.lower() for t in custom_terms}

    for i, word in enumerate(words):
        # Strip punctuation for comparison
        clean = re.sub(r"[^a-zA-Z0-9]", "", word)
        if not clean:
            continue

        # First word must be capitalized
        if i == 0:
            if not clean[0].isupper():
                return False
            continue

        # Allow all-caps words (acronyms: API, MCP, CLI, etc.)
        if clean.isupper() and len(clean) > 1:
            continue

        # Allow custom terms
        if clean.lower() in custom_set:
            continue

        # Allow words with mixed case that look like identifiers (camelCase, PascalCase)
        if any(c.isupper() for c in clean[1:]) and any(c.islower() for c in clean):
            continue

        # Remaining words should be lowercase
        if clean[0].isupper():
            return False

    return True


def _is_title_case(text: str, custom_terms: list[str]) -> bool:
    """Check if text follows title case.

    Major words capitalized, articles/prepositions lowercase (except first word).
    """
    words = text.split()
    if not words:
        return True

    custom_set = {t.lower() for t in custom_terms}

    for i, word in enumerate(words):
        clean = re.sub(r"[^a-zA-Z0-9]", "", word)
        if not clean:
            continue

        # Allow all-caps words (acronyms)
        if clean.isupper() and len(clean) > 1:
            continue

        # Allow custom terms
        if clean.lower() in custom_set:
            continue

        # First word must be capitalized
        if i == 0:
            if not clean[0].isupper():
                return False
            continue

        # Articles/prepositions can be lowercase
        if clean.lower() in _TITLE_CASE_EXCEPTIONS:
            continue

        # Major words must be capitalized
        if not clean[0].isupper():
            return False

    return True


def _calculate_file_score(issues: list[StyleIssue]) -> float:
    """Calculate a file style score (0-100) from issues.

    Errors deduct 10 points, warnings 5, suggestions 2.
    """
    deductions = 0.0
    for issue in issues:
        if issue.severity == "error":
            deductions += 10.0
        elif issue.severity == "warning":
            deductions += 5.0
        else:
            deductions += 2.0

    return max(0.0, round(100.0 - deductions, 1))
