"""Diataxis content classification for documentation files.

Classifies markdown documents into the four Diataxis quadrants:
- Tutorial (learning-oriented, practical)
- How-to Guide (task-oriented, practical)
- Reference (information-oriented, theoretical)
- Explanation (understanding-oriented, theoretical)

Uses deterministic heuristics (heading patterns, content indicators,
structural analysis) -- no LLM calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class DiataxisResult(BaseModel):
    """Classification result for a single document."""

    file_path: str
    primary_quadrant: str  # "tutorial", "how-to", "reference", "explanation"
    confidence: float  # 0.0-1.0
    secondary_quadrant: str = ""
    indicators: list[str] = []
    is_mixed: bool = False


class DiataxisCoverage(BaseModel):
    """Coverage map across all four quadrants for a project."""

    tutorial_pct: float = 0.0
    howto_pct: float = 0.0
    reference_pct: float = 0.0
    explanation_pct: float = 0.0
    balance_score: float = 0.0  # 0-100, higher = better balance
    total_files: int = 0
    classified_files: int = 0
    per_file: list[DiataxisResult] = []
    recommendations: list[str] = []


class DiataxisClassifier:
    """Deterministic classifier for Diataxis content quadrants.

    Scoring is based on three signal types:
    1. Heading patterns (strongest signal)
    2. Content keyword density
    3. Structural patterns (numbered steps, tables, code blocks)
    """

    # Heading patterns per quadrant (case-insensitive regexes)
    _HEADING_PATTERNS: ClassVar[dict[str, list[re.Pattern[str]]]] = {
        "tutorial": [
            re.compile(r"getting\s+started", re.IGNORECASE),
            re.compile(r"step\s+\d", re.IGNORECASE),
            re.compile(r"tutorial", re.IGNORECASE),
            re.compile(r"walkthrough", re.IGNORECASE),
            re.compile(r"learn\b", re.IGNORECASE),
            re.compile(r"your\s+first", re.IGNORECASE),
            re.compile(r"beginner", re.IGNORECASE),
            re.compile(r"introduction\s+to", re.IGNORECASE),
        ],
        "how-to": [
            re.compile(r"how\s+to\b", re.IGNORECASE),
            re.compile(r"guide\b", re.IGNORECASE),
            re.compile(r"recipe\b", re.IGNORECASE),
            re.compile(r"configure\b", re.IGNORECASE),
            re.compile(r"set\s*up\b", re.IGNORECASE),
            re.compile(r"install\b", re.IGNORECASE),
            re.compile(r"deploy\b", re.IGNORECASE),
            re.compile(r"migrat", re.IGNORECASE),
        ],
        "reference": [
            re.compile(r"\bapi\b", re.IGNORECASE),
            re.compile(r"reference\b", re.IGNORECASE),
            re.compile(r"specification\b", re.IGNORECASE),
            re.compile(r"parameters?\b", re.IGNORECASE),
            re.compile(r"returns?\b", re.IGNORECASE),
            re.compile(r"class\b.*\(", re.IGNORECASE),
            re.compile(r"method\b", re.IGNORECASE),
            re.compile(r"endpoint", re.IGNORECASE),
        ],
        "explanation": [
            re.compile(r"\bwhy\b", re.IGNORECASE),
            re.compile(r"background\b", re.IGNORECASE),
            re.compile(r"architecture\b", re.IGNORECASE),
            re.compile(r"design\b", re.IGNORECASE),
            re.compile(r"concept", re.IGNORECASE),
            re.compile(r"overview\b", re.IGNORECASE),
            re.compile(r"philosophy", re.IGNORECASE),
            re.compile(r"decision\b", re.IGNORECASE),
        ],
    }

    # Content keywords per quadrant
    _CONTENT_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "tutorial": [
            "let's",
            "we will",
            "you will learn",
            "in this tutorial",
            "follow along",
            "hands-on",
            "exercise",
            "practice",
            "by the end",
            "prerequisite",
        ],
        "how-to": [
            "run the following",
            "execute",
            "create a",
            "add the",
            "modify",
            "update the",
            "ensure that",
            "verify",
            "troubleshoot",
            "resolve",
        ],
        "reference": [
            "type:",
            "default:",
            "required:",
            "optional:",
            "raises:",
            "returns:",
            "args:",
            "parameters:",
            "enum",
            "schema",
            "payload",
        ],
        "explanation": [
            "the reason",
            "this is because",
            "trade-off",
            "tradeoff",
            "compared to",
            "alternative",
            "motivation",
            "in contrast",
            "historically",
            "evolution",
        ],
    }

    # Structural signals
    _NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+", re.MULTILINE)
    _CODE_BLOCK_RE = re.compile(r"```", re.MULTILINE)
    _TABLE_RE = re.compile(r"^\|.*\|.*\|", re.MULTILINE)
    _PARAM_TABLE_RE = re.compile(r"^\|\s*\w+\s*\|.*\|.*\|", re.MULTILINE)

    def classify(self, content: str, file_path: str = "") -> DiataxisResult:
        """Classify a single document into a Diataxis quadrant.

        Args:
            content: The markdown file content.
            file_path: Optional file path for additional context.

        Returns:
            DiataxisResult with primary quadrant and confidence.
        """
        # Check frontmatter override first
        fm_type = self._check_frontmatter_override(content)
        if fm_type:
            return DiataxisResult(
                file_path=file_path,
                primary_quadrant=fm_type,
                confidence=1.0,
                indicators=["frontmatter_override"],
            )

        # Score each quadrant
        scores: dict[str, float] = {
            "tutorial": 0.0,
            "how-to": 0.0,
            "reference": 0.0,
            "explanation": 0.0,
        }
        indicators: dict[str, list[str]] = {q: [] for q in scores}

        # Extract headings
        headings = re.findall(r"^#{1,3}\s+(.+)$", content, re.MULTILINE)

        # 1. Heading pattern scoring (weight: 3.0 per match)
        for quadrant, patterns in self._HEADING_PATTERNS.items():
            for heading in headings:
                for pattern in patterns:
                    if pattern.search(heading):
                        scores[quadrant] += 3.0
                        indicators[quadrant].append(f"heading:{heading[:40]}")
                        break  # One match per heading per quadrant

        # 2. Content keyword scoring (weight: 1.5 per match)
        content_lower = content.lower()
        for quadrant, keywords in self._CONTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in content_lower:
                    scores[quadrant] += 1.5
                    indicators[quadrant].append(f"keyword:{kw}")

        # 3. Structural scoring
        self._score_structural_signals(content, scores, indicators)

        # 4. Filename hints (weight: 1.0)
        if file_path:
            self._score_filename_hints(file_path, scores, indicators)

        # Find primary and secondary
        sorted_q = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_q[0]
        secondary = sorted_q[1] if len(sorted_q) > 1 else ("", 0.0)

        total_score = sum(scores.values())
        if total_score == 0:
            return DiataxisResult(
                file_path=file_path,
                primary_quadrant="explanation",  # Default fallback
                confidence=0.1,
                indicators=["no_signals"],
            )

        confidence = primary[1] / total_score if total_score > 0 else 0.0
        is_mixed = secondary[1] > 0 and primary[1] > 0 and secondary[1] / primary[1] > 0.6

        return DiataxisResult(
            file_path=file_path,
            primary_quadrant=primary[0],
            confidence=round(min(confidence, 1.0), 2),
            secondary_quadrant=secondary[0] if is_mixed else "",
            indicators=indicators[primary[0]][:5],
            is_mixed=is_mixed,
        )

    def _score_structural_signals(
        self,
        content: str,
        scores: dict[str, float],
        indicators: dict[str, list[str]],
    ) -> None:
        """Apply structural heuristic scores (numbered steps, tables, code blocks, prose)."""
        numbered_steps = len(self._NUMBERED_STEP_RE.findall(content))
        code_blocks = len(self._CODE_BLOCK_RE.findall(content)) // 2  # pairs
        tables = len(self._TABLE_RE.findall(content))
        param_tables = len(self._PARAM_TABLE_RE.findall(content))

        # Tutorials have many numbered steps + code blocks
        if numbered_steps >= 3:
            scores["tutorial"] += 2.0
            indicators["tutorial"].append(f"structure:numbered_steps({numbered_steps})")
        if code_blocks >= 3 and numbered_steps >= 2:
            scores["tutorial"] += 1.5
            indicators["tutorial"].append("structure:code_with_steps")

        # How-to has code blocks but fewer steps
        if code_blocks >= 1 and numbered_steps < 3:
            scores["how-to"] += 1.0
            indicators["how-to"].append("structure:code_blocks")

        # Reference has parameter tables
        if param_tables >= 2:
            scores["reference"] += 3.0
            indicators["reference"].append(f"structure:param_tables({param_tables})")
        elif tables >= 2:
            scores["reference"] += 1.5
            indicators["reference"].append(f"structure:tables({tables})")

        # Explanation has fewer code blocks, more prose
        lines = content.split("\n")
        prose_lines = sum(
            1
            for ln in lines
            if ln.strip() and not ln.strip().startswith(("#", "-", "*", "|", "`", ">"))
        )
        if prose_lines > len(lines) * 0.6 and code_blocks < 2:
            scores["explanation"] += 1.5
            indicators["explanation"].append("structure:prose_heavy")

    def _score_filename_hints(
        self,
        file_path: str,
        scores: dict[str, float],
        indicators: dict[str, list[str]],
    ) -> None:
        """Apply filename-based hint scores (weight: 1.0 per matched hint)."""
        path_lower = file_path.lower()
        name_hints: dict[str, list[str]] = {
            "tutorial": ["tutorial", "learn", "getting-started", "quickstart"],
            "how-to": ["howto", "how-to", "guide", "cookbook", "recipe"],
            "reference": ["reference", "api", "spec", "schema"],
            "explanation": ["explanation", "concept", "architecture", "design", "adr"],
        }
        for quadrant, hints in name_hints.items():
            if any(h in path_lower for h in hints):
                scores[quadrant] += 1.0
                indicators[quadrant].append(f"filename:{Path(file_path).name}")

    def _check_frontmatter_override(self, content: str) -> str:
        """Check for diataxis_type in YAML frontmatter."""
        fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not fm_match:
            return ""

        fm_text = fm_match.group(1)
        for line in fm_text.split("\n"):
            if line.strip().startswith("diataxis_type:"):
                value = line.split(":", 1)[1].strip().strip("\"'")
                if value in ("tutorial", "how-to", "reference", "explanation"):
                    return value
        return ""
