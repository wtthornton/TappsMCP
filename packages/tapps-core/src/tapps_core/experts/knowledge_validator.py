"""Knowledge base file validator.

Validates markdown knowledge files for structural quality, correct
Python code blocks, cross-reference integrity, and formatting.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# Validation thresholds.
_MAX_FILE_SIZE = 100 * 1024  # 100 KB warning


class ValidationIssue(BaseModel):
    """A single validation issue found in a knowledge file."""

    file_path: str = Field(description="Path to the file.")
    severity: str = Field(description="Severity: error, warning, or info.")
    line_number: int | None = Field(default=None, description="Line number (1-indexed).")
    message: str = Field(description="Human-readable description.")
    rule: str = Field(description="Machine-readable rule identifier.")


class ValidationResult(BaseModel):
    """Result of validating a single knowledge file."""

    file_path: str = Field(description="Path to the file.")
    is_valid: bool = Field(description="True if no errors were found.")
    issues: list[ValidationIssue] = Field(default_factory=list, description="All issues found.")
    file_size: int = Field(default=0, ge=0, description="File size in bytes.")
    line_count: int = Field(default=0, ge=0, description="Number of lines.")
    has_headers: bool = Field(default=False, description="Whether the file has markdown headers.")
    has_code_blocks: bool = Field(default=False, description="Whether the file has code blocks.")
    has_examples: bool = Field(default=False, description="Whether the file has examples.")


class KnowledgeBaseValidator:
    """Validates knowledge base markdown files."""

    def __init__(self, knowledge_dir: Path) -> None:
        self._knowledge_dir = knowledge_dir

    def validate_all(self) -> list[ValidationResult]:
        """Validate all ``*.md`` files in the knowledge directory."""
        if not self._knowledge_dir.exists():
            return []

        results: list[ValidationResult] = []
        for md_file in sorted(self._knowledge_dir.rglob("*.md")):
            results.append(self.validate_file(md_file))
        return results

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a single knowledge file."""
        issues: list[ValidationIssue] = []
        path_str = str(file_path)

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(
                ValidationIssue(
                    file_path=path_str,
                    severity="error",
                    message=f"Cannot read file: {exc}",
                    rule="file_readable",
                )
            )
            return ValidationResult(file_path=path_str, is_valid=False, issues=issues)

        file_size = len(content.encode("utf-8"))
        lines = content.split("\n")
        line_count = len(lines)

        # Detect structural features.
        has_headers = any(line.strip().startswith("#") for line in lines)
        has_code_blocks = "```" in content
        has_examples = bool(re.search(r"(?i)(example|e\.g\.|for instance)", content))

        # Run validations.
        issues.extend(self._validate_structure(content, file_path))
        issues.extend(self._validate_markdown_syntax(content, file_path))
        issues.extend(self._validate_code_blocks(content, file_path))
        issues.extend(self._validate_cross_references(content, file_path, self._knowledge_dir))

        # File size check.
        if file_size > _MAX_FILE_SIZE:
            issues.append(
                ValidationIssue(
                    file_path=path_str,
                    severity="warning",
                    message=f"File size ({file_size} bytes) exceeds {_MAX_FILE_SIZE} bytes",
                    rule="file_size",
                )
            )

        is_valid = not any(i.severity == "error" for i in issues)

        return ValidationResult(
            file_path=path_str,
            is_valid=is_valid,
            issues=issues,
            file_size=file_size,
            line_count=line_count,
            has_headers=has_headers,
            has_code_blocks=has_code_blocks,
            has_examples=has_examples,
        )

    @staticmethod
    def _validate_structure(
        content: str,
        file_path: Path,
    ) -> list[ValidationIssue]:
        """Check for title header and proper hierarchy."""
        issues: list[ValidationIssue] = []
        path_str = str(file_path)
        lines = content.split("\n")

        # Check for H1 title.
        has_h1 = any(
            line.strip().startswith("# ") and not line.strip().startswith("##") for line in lines
        )
        if not has_h1:
            issues.append(
                ValidationIssue(
                    file_path=path_str,
                    severity="info",
                    message="No H1 title found",
                    rule="has_title",
                )
            )

        # Check header hierarchy (no skips like H1 -> H3).
        prev_level = 0
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                if prev_level > 0 and level > prev_level + 1:
                    issues.append(
                        ValidationIssue(
                            file_path=path_str,
                            severity="warning",
                            line_number=i,
                            message=f"Header level skip: H{prev_level} -> H{level}",
                            rule="header_hierarchy",
                        )
                    )
                prev_level = level

        return issues

    @staticmethod
    def _validate_markdown_syntax(
        content: str,
        file_path: Path,
    ) -> list[ValidationIssue]:
        """Check for unclosed code blocks."""
        issues: list[ValidationIssue] = []
        path_str = str(file_path)

        # Count code block markers (```)
        fence_count = len(re.findall(r"^```", content, re.MULTILINE))
        if fence_count % 2 != 0:
            issues.append(
                ValidationIssue(
                    file_path=path_str,
                    severity="error",
                    message=f"Unclosed code block ({fence_count} fence markers)",
                    rule="code_block_closed",
                )
            )

        return issues

    @staticmethod
    def _validate_code_blocks(
        content: str,
        file_path: Path,
    ) -> list[ValidationIssue]:
        """Validate Python code blocks via AST parsing."""
        issues: list[ValidationIssue] = []
        path_str = str(file_path)

        # Extract Python code blocks.
        pattern = re.compile(r"^```python\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
        for match in pattern.finditer(content):
            code = match.group(1)
            # Find the line number of this code block.
            line_num = content[: match.start()].count("\n") + 1

            try:
                ast.parse(code)
            except SyntaxError as exc:
                issues.append(
                    ValidationIssue(
                        file_path=path_str,
                        severity="error",
                        line_number=line_num + (exc.lineno or 0),
                        message=f"Python syntax error: {exc.msg}",
                        rule="python_syntax",
                    )
                )

        return issues

    @staticmethod
    def _validate_cross_references(
        content: str,
        file_path: Path,
        knowledge_dir: Path,
    ) -> list[ValidationIssue]:
        """Check markdown links to other knowledge files."""
        issues: list[ValidationIssue] = []
        path_str = str(file_path)

        # Find markdown links: [text](path.md)
        link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")
        for match in link_pattern.finditer(content):
            ref_path = match.group(2)
            # Skip URLs.
            if ref_path.startswith(("http://", "https://")):
                continue

            target = (file_path.parent / ref_path).resolve()
            if not target.exists():
                line_num = content[: match.start()].count("\n") + 1
                issues.append(
                    ValidationIssue(
                        file_path=path_str,
                        severity="warning",
                        line_number=line_num,
                        message=f"Broken cross-reference: {ref_path}",
                        rule="cross_reference",
                    )
                )

        return issues

    @staticmethod
    def get_summary(results: list[ValidationResult]) -> dict[str, Any]:
        """Aggregate validation results into a summary."""
        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        error_count = sum(1 for r in results for i in r.issues if i.severity == "error")
        warning_count = sum(1 for r in results for i in r.issues if i.severity == "warning")
        info_count = sum(1 for r in results for i in r.issues if i.severity == "info")

        return {
            "total_files": total,
            "valid_files": valid,
            "invalid_files": total - valid,
            "errors": error_count,
            "warnings": warning_count,
            "info": info_count,
        }
