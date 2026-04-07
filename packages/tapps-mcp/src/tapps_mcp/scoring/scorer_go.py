"""Go code scorer.

Scores Go files across quality categories using tree-sitter parsing
for AST-based analysis.

Epic 56: Non-Python Language Scoring
Story 56.4: Go Scorer
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.scoring.constants import clamp_individual, clamp_overall
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.scoring.scorer_base import ScorerBase

if TYPE_CHECKING:
    from tapps_core.config.settings import ScoringWeights, TappsMCPSettings

logger = structlog.get_logger(__name__)

# Guard tree-sitter imports for graceful degradation
_GO_LANGUAGE: Any = None
try:
    import tree_sitter
    import tree_sitter_go

    _GO_LANGUAGE = tree_sitter.Language(tree_sitter_go.language())
    HAS_TREE_SITTER = True
except ImportError:
    tree_sitter = None  # type: ignore[assignment]
    HAS_TREE_SITTER = False

# Categories supported by the Go scorer
_GO_CATEGORIES: list[str] = [
    "complexity",
    "security",
    "maintainability",
    "test_coverage",
    "performance",
    "structure",
    "devex",
]

# Security patterns to detect in Go code
_SECURITY_PATTERNS: list[tuple[str, str]] = [
    (r"unsafe\.Pointer", "unsafe.Pointer usage"),
    (r"os\.Exec\s*\(", "os.Exec usage"),
    (r"exec\.Command\s*\(", "exec.Command usage"),
    (r"fmt\.Sprintf\s*\([^,]*%s.*,\s*\w+\)", "potential SQL injection via Sprintf"),
    (r'sql\.Query\s*\([^,]*"\s*\+', "SQL string concatenation"),
    (r"http\.Get\s*\(\s*\w+\s*\)", "unvalidated URL in http.Get"),
    (r"ioutil\.ReadAll", "ioutil.ReadAll (memory exhaustion risk)"),
    (r"#nosec", "nosec directive (security check bypassed)"),
]

# Performance anti-patterns
_PERFORMANCE_PATTERNS: list[tuple[str, str]] = [
    (r"defer\s+.*\bfor\b", "defer in loop"),
    (r"append\s*\([^,]+,\s*[^)]+\.\.\.\s*\)", "append with spread in loop"),
    (r"string\s*\(\s*\[\s*\]byte", "string/[]byte conversion"),
]

# Max file size to parse (10 MB)
_MAX_FILE_SIZE = 10 * 1024 * 1024


class GoScorer(ScorerBase):
    """Score Go files across quality categories.

    This scorer handles .go files. It uses tree-sitter parsing
    for AST-based analysis when available.

    Categories scored:
    - complexity: Cyclomatic complexity via AST branch counting
    - security: Pattern detection (unsafe.Pointer, os.Exec, SQL injection)
    - maintainability: Doc comments, exported vs unexported ratio
    - test_coverage: Test file detection (*_test.go), Test* function count
    - performance: Defer in loops, goroutine leaks
    - structure: Package imports, nesting depth
    - devex: Naming conventions (MixedCaps), error handling patterns
    """

    def __init__(
        self,
        settings: TappsMCPSettings | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        """Initialize the Go scorer."""
        super().__init__(settings, weights)

    @property
    def language(self) -> str:
        """Return 'go' as the language identifier."""
        return "go"

    @property
    def supported_categories(self) -> list[str]:
        """Return the categories supported by this scorer."""
        return _GO_CATEGORIES.copy()

    @property
    def file_extensions(self) -> frozenset[str]:
        """Return Go file extensions."""
        return frozenset({".go"})

    def score_file_quick(self, file_path: Path) -> ScoreResult:
        """Quick mode scoring for Go files.

        Uses regex-based analysis for fast feedback.
        Target latency is < 500ms.

        Args:
            file_path: Path to the file to score.

        Returns:
            A ScoreResult with quick-mode scoring.
        """
        resolved = file_path.resolve()
        try:
            code = resolved.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            logger.error("file_read_failed", path=str(resolved), error=str(exc))
            return self._error_result(str(resolved))

        # Quick mode: regex-based lint check
        issues = self._regex_lint_check(code)
        lint_score = clamp_individual(10.0 - len(issues) * 0.5)

        categories = {
            "linting": CategoryScore(
                name="linting",
                score=lint_score,
                weight=1.0,
                details={"issue_count": len(issues), "issues": issues[:10]},
            ),
        }

        return ScoreResult(
            file_path=str(resolved),
            categories=categories,
            overall_score=clamp_overall(lint_score * 10.0),
            degraded=False,
            language="go",
        )

    async def score_file(self, file_path: Path, *, mode: str = "subprocess") -> ScoreResult:
        """Full mode scoring for Go files.

        Uses tree-sitter parsing when available for comprehensive analysis.

        Args:
            file_path: Path to the file to score.
            mode: Execution mode (reserved for future linter integration).

        Returns:
            A ScoreResult with full scoring.
        """
        resolved = file_path.resolve()
        str_path = str(resolved)

        # Check file size
        try:
            size = resolved.stat().st_size
            if size > _MAX_FILE_SIZE:
                logger.warning("file_too_large", path=str_path, size=size)
                return self._error_result(str_path)
        except OSError:
            return self._error_result(str_path)

        # Read file content
        try:
            code = await asyncio.to_thread(
                resolved.read_text, encoding="utf-8", errors="replace"
            )
        except (OSError, PermissionError) as exc:
            logger.error("file_read_failed", path=str_path, error=str(exc))
            return self._error_result(str_path)

        # Build category scores
        if HAS_TREE_SITTER:
            categories = self._score_with_treesitter(code, resolved)
            degraded = False
            missing_tools: list[str] = []
        else:
            categories = self._score_with_regex(code, resolved)
            degraded = True
            missing_tools = ["tree-sitter"]

        overall = self._calculate_overall(categories)

        return ScoreResult(
            file_path=str_path,
            categories=categories,
            overall_score=overall,
            degraded=degraded,
            missing_tools=missing_tools,
            language="go",
        )

    # ------------------------------------------------------------------
    # Tree-sitter based scoring
    # ------------------------------------------------------------------

    def _score_with_treesitter(
        self, code: str, file_path: Path
    ) -> dict[str, CategoryScore]:
        """Score using tree-sitter AST analysis."""
        source_bytes = code.encode("utf-8")
        parser = tree_sitter.Parser(_GO_LANGUAGE)
        tree = parser.parse(source_bytes)
        root = tree.root_node

        w = self._weights
        cats: dict[str, CategoryScore] = {}

        # 1) Complexity
        cats["complexity"] = self._score_complexity_go(root, source_bytes, w.complexity)

        # 2) Security
        cats["security"] = self._score_security_go(code, root, source_bytes, w.security)

        # 3) Maintainability
        cats["maintainability"] = self._score_maintainability_go(
            code, root, source_bytes, w.maintainability
        )

        # 4) Test coverage
        cats["test_coverage"] = self._score_test_coverage_go(
            file_path, code, root, source_bytes, w.test_coverage
        )

        # 5) Performance
        cats["performance"] = self._score_performance_go(code, root, source_bytes, w.performance)

        # 6) Structure
        cats["structure"] = self._score_structure_go(root, source_bytes, file_path, w.structure)

        # 7) DevEx
        cats["devex"] = self._score_devex_go(code, root, source_bytes, w.devex)

        return cats

    def _score_complexity_go(
        self, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate complexity score via AST branch counting."""
        branch_types = {
            "if_statement",
            "for_statement",
            "switch_statement",
            "type_switch_statement",
            "select_statement",
            "expression_case",
            "default_case",
        }

        function_complexities: list[int] = []

        def count_branches(node: Any) -> int:
            """Count branches in a node recursively."""
            count = 0
            if node.type in branch_types:
                count = 1
            # Count && and || in binary expressions
            if node.type == "binary_expression":
                for child in node.children:
                    if child.type in ("&&", "||"):
                        count += 1
            for child in node.children:
                count += count_branches(child)
            return count

        # Find all functions and calculate their complexity
        for node in self._walk_tree(root):
            if node.type in ("function_declaration", "method_declaration"):
                cc = 1 + count_branches(node)
                function_complexities.append(cc)

        if function_complexities:
            max_cc = max(function_complexities)
            avg_cc = sum(function_complexities) / len(function_complexities)
        else:
            max_cc = 1 + count_branches(root)
            avg_cc = max_cc

        score = clamp_individual(max_cc / 5.0)

        return CategoryScore(
            name="complexity",
            score=score,
            weight=weight,
            details={
                "max_cc": max_cc,
                "avg_cc": round(avg_cc, 2),
                "function_count": len(function_complexities),
            },
            suggestions=self._suggest_complexity(max_cc),
        )

    def _score_security_go(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate security score via pattern detection."""
        issues_found: list[str] = []

        # Regex-based pattern detection
        for pattern, description in _SECURITY_PATTERNS:
            if re.search(pattern, code):
                issues_found.append(description)

        # AST-based detection for more accuracy
        for node in self._walk_tree(root):
            # Detect unsafe package usage
            if node.type == "selector_expression":
                text = source[node.start_byte:node.end_byte].decode()
                if text.startswith("unsafe.") and "unsafe" not in str(issues_found):
                    if "unsafe.Pointer usage" not in issues_found:
                        issues_found.append("unsafe package usage")

        penalty = len(issues_found) * 2.0
        score = clamp_individual(10.0 - penalty)

        return CategoryScore(
            name="security",
            score=score,
            weight=weight,
            details={"issues_found": issues_found, "issue_count": len(issues_found)},
            suggestions=self._suggest_security(issues_found),
        )

    def _score_maintainability_go(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate maintainability score."""
        lines = code.splitlines()
        line_count = len(lines)

        # Count doc comments (// style preceding declarations)
        doc_comment_count = 0
        exported_count = 0
        documented_exported = 0

        for node in self._walk_tree(root):
            if node.type in ("function_declaration", "method_declaration", "type_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source[name_node.start_byte:name_node.end_byte].decode()
                    # Exported if starts with uppercase
                    if name and name[0].isupper():
                        exported_count += 1
                        # Check for preceding comment
                        if self._has_doc_comment(node, root, source):
                            documented_exported += 1
                            doc_comment_count += 1

        doc_ratio = documented_exported / max(exported_count, 1)

        # Start with base score
        score = 8.0

        # Penalize for large files
        if line_count > 500:
            score -= 2.0
        elif line_count > 300:
            score -= 1.0

        # Reward for documentation
        if doc_ratio >= 0.8:
            score += 1.0
        elif doc_ratio < 0.5:
            score -= 1.0

        score = clamp_individual(score)

        return CategoryScore(
            name="maintainability",
            score=score,
            weight=weight,
            details={
                "line_count": line_count,
                "exported_count": exported_count,
                "documented_exported": documented_exported,
                "doc_ratio": round(doc_ratio, 2),
            },
            suggestions=self._suggest_maintainability(doc_ratio, exported_count),
        )

    def _score_test_coverage_go(
        self, file_path: Path, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate test coverage heuristic score."""
        name = file_path.name.lower()

        # Check if this is a test file
        is_test_file = name.endswith("_test.go")

        if is_test_file:
            # Count Test* functions
            test_count = 0
            for node in self._walk_tree(root):
                if node.type == "function_declaration":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = source[name_node.start_byte:name_node.end_byte].decode()
                        if func_name.startswith("Test"):
                            test_count += 1
            score = 5.0  # Neutral for test files
            details: dict[str, object] = {"is_test_file": True, "test_function_count": test_count}
        else:
            # Check if corresponding test file exists
            test_file = file_path.parent / f"{file_path.stem}_test.go"
            has_test = test_file.exists()
            score = 5.0 if has_test else 0.0
            details = {"is_test_file": False, "has_test_file": has_test}

        return CategoryScore(
            name="test_coverage",
            score=score,
            weight=weight,
            details=details,
            suggestions=[] if is_test_file or score > 0 else ["Consider adding tests"],
        )

    def _score_performance_go(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate performance score via pattern detection."""
        issues_found: list[str] = []

        # Regex-based detection
        for pattern, description in _PERFORMANCE_PATTERNS:
            if re.search(pattern, code):
                issues_found.append(description)

        # AST-based detection for defer in loops
        for node in self._walk_tree(root):
            if node.type == "for_statement":
                for child in self._walk_tree(node):
                    if child.type == "defer_statement":
                        if "defer in loop" not in issues_found:
                            issues_found.append("defer in loop")
                        break

        # Check for goroutine leaks (go func without context)
        goroutine_count = len(re.findall(r"\bgo\s+func\s*\(", code))
        ctx_count = len(re.findall(r"context\.(Context|WithCancel|WithTimeout)", code))
        if goroutine_count > 2 and ctx_count == 0:
            issues_found.append("goroutines without context (potential leaks)")

        penalty = len(issues_found) * 1.5
        score = clamp_individual(10.0 - penalty)

        return CategoryScore(
            name="performance",
            score=score,
            weight=weight,
            details={"issues_found": issues_found, "goroutine_count": goroutine_count},
            suggestions=self._suggest_performance(issues_found),
        )

    def _score_structure_go(
        self, root: Any, source: bytes, file_path: Path, weight: float
    ) -> CategoryScore:
        """Calculate structure score."""
        # Count imports
        import_count = 0
        for node in root.children:
            if node.type == "import_declaration":
                # Count individual imports in an import block
                for child in self._walk_tree(node):
                    if child.type == "import_spec":
                        import_count += 1
                if import_count == 0:
                    import_count = 1  # Single import

        # Check nesting depth
        max_depth = self._max_nesting_depth(root)

        # Start with base score
        score = 8.0

        # Penalize for excessive imports
        if import_count > 20:
            score -= 2.0
        elif import_count > 15:
            score -= 1.0

        # Penalize for deep nesting
        if max_depth > 5:
            score -= 2.0
        elif max_depth > 4:
            score -= 1.0

        # Bonus for being in a well-structured project
        if (file_path.parent / "go.mod").exists():
            score += 0.5
        if (file_path.parent / "go.sum").exists():
            score += 0.5

        score = clamp_individual(score)

        return CategoryScore(
            name="structure",
            score=score,
            weight=weight,
            details={
                "import_count": import_count,
                "max_nesting_depth": max_depth,
            },
        )

    def _score_devex_go(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate developer experience score."""
        issues: list[str] = []

        # Check error handling patterns
        # Count error returns that are ignored (_, err := ... without if err != nil)
        err_assignments = len(re.findall(r",\s*err\s*:=", code))
        err_checks = len(re.findall(r"if\s+err\s*!=\s*nil", code))

        if err_assignments > 0 and err_checks < err_assignments * 0.8:
            issues.append("some errors may not be handled")

        # Check for blank identifier overuse
        blank_count = len(re.findall(r"_\s*,|,\s*_\s*:=|_\s*:=", code))
        if blank_count > 5:
            issues.append(f"excessive blank identifier usage ({blank_count})")

        # Check naming conventions (Go uses MixedCaps, not snake_case)
        snake_exports = len(re.findall(r"\bfunc\s+[A-Z][a-z]+_[A-Z]", code))
        if snake_exports > 0:
            issues.append("snake_case in exported names (use MixedCaps)")

        score = 8.0
        if issues:
            score -= len(issues) * 0.5

        score = clamp_individual(score)

        return CategoryScore(
            name="devex",
            score=score,
            weight=weight,
            details={
                "err_assignments": err_assignments,
                "err_checks": err_checks,
                "issues": issues,
            },
            suggestions=self._suggest_devex(issues),
        )

    # ------------------------------------------------------------------
    # Regex-based fallback scoring
    # ------------------------------------------------------------------

    def _score_with_regex(
        self, code: str, file_path: Path
    ) -> dict[str, CategoryScore]:
        """Score using regex-based analysis (fallback when tree-sitter unavailable)."""
        w = self._weights
        cats: dict[str, CategoryScore] = {}

        lines = code.splitlines()
        line_count = len(lines)

        # 1) Complexity (regex approximation)
        branch_count = sum([
            len(re.findall(r"\bif\s+", code)),
            len(re.findall(r"\bfor\s+", code)),
            len(re.findall(r"\bswitch\s+", code)),
            len(re.findall(r"\bselect\s*\{", code)),
            len(re.findall(r"\bcase\s+", code)),
        ])
        complexity_score = clamp_individual(branch_count / 5.0)
        cats["complexity"] = CategoryScore(
            name="complexity",
            score=complexity_score,
            weight=w.complexity,
            details={"branch_count": branch_count, "fallback": True},
        )

        # 2) Security
        security_issues: list[str] = []
        for pattern, description in _SECURITY_PATTERNS:
            if re.search(pattern, code):
                security_issues.append(description)
        security_score = clamp_individual(10.0 - len(security_issues) * 2.0)
        cats["security"] = CategoryScore(
            name="security",
            score=security_score,
            weight=w.security,
            details={"issues_found": security_issues, "fallback": True},
        )

        # 3) Maintainability
        # Count doc comments (// preceding exported names)
        doc_comments = len(re.findall(r"//\s*\w+.*\n\s*func\s+[A-Z]", code))
        maint_score = 8.0
        if line_count > 500:
            maint_score -= 2.0
        elif line_count > 300:
            maint_score -= 1.0
        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=clamp_individual(maint_score),
            weight=w.maintainability,
            details={"line_count": line_count, "doc_comments": doc_comments, "fallback": True},
        )

        # 4) Test coverage
        is_test = file_path.name.endswith("_test.go")
        cats["test_coverage"] = CategoryScore(
            name="test_coverage",
            score=5.0 if is_test else 0.0,
            weight=w.test_coverage,
            details={"is_test_file": is_test, "fallback": True},
        )

        # 5) Performance
        perf_issues: list[str] = []
        for pattern, description in _PERFORMANCE_PATTERNS:
            if re.search(pattern, code):
                perf_issues.append(description)
        cats["performance"] = CategoryScore(
            name="performance",
            score=clamp_individual(10.0 - len(perf_issues) * 1.5),
            weight=w.performance,
            details={"issues_found": perf_issues, "fallback": True},
        )

        # 6) Structure
        import_count = len(re.findall(r'"\w+[/\w]*"', code))  # Count import paths
        struct_score = 8.0
        if import_count > 20:
            struct_score -= 2.0
        elif import_count > 15:
            struct_score -= 1.0
        cats["structure"] = CategoryScore(
            name="structure",
            score=clamp_individual(struct_score),
            weight=w.structure,
            details={"import_count": import_count, "fallback": True},
        )

        # 7) DevEx
        err_handling = len(re.findall(r"if\s+err\s*!=\s*nil", code))
        devex_score = 8.0 if err_handling > 0 else 6.0
        cats["devex"] = CategoryScore(
            name="devex",
            score=clamp_individual(devex_score),
            weight=w.devex,
            details={"err_checks": err_handling, "fallback": True},
        )

        return cats

    def _regex_lint_check(self, code: str) -> list[str]:
        """Quick regex-based lint check for common issues."""
        issues: list[str] = []

        # Check for fmt.Print (should use log or structured logging)
        if re.search(r"fmt\.Print", code):
            issues.append("fmt.Print found (consider logging)")

        # Check for panic
        if re.search(r"\bpanic\s*\(", code):
            issues.append("panic() usage (handle errors gracefully)")

        # Check for TODO/FIXME
        if re.search(r"//\s*(TODO|FIXME|XXX|HACK)\b", code, re.IGNORECASE):
            issues.append("TODO/FIXME comment found")

        # Check for unsafe package
        if re.search(r'"unsafe"', code):
            issues.append("unsafe package imported")

        return issues

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _walk_tree(self, node: Any) -> list[Any]:
        """Walk tree-sitter AST and yield all nodes."""
        nodes = [node]
        for child in node.children:
            nodes.extend(self._walk_tree(child))
        return nodes

    def _max_nesting_depth(self, node: Any, depth: int = 0) -> int:
        """Calculate maximum nesting depth of control structures."""
        control_types = {
            "if_statement",
            "for_statement",
            "switch_statement",
            "type_switch_statement",
            "select_statement",
        }
        max_d = depth
        for child in node.children:
            if child.type in control_types:
                max_d = max(max_d, self._max_nesting_depth(child, depth + 1))
            else:
                max_d = max(max_d, self._max_nesting_depth(child, depth))
        return max_d

    def _has_doc_comment(self, node: Any, root: Any, source: bytes) -> bool:
        """Check if a node has a doc comment preceding it."""
        # Look for comment immediately before the node
        node_line = node.start_point[0]
        for child in root.children:
            if child.type == "comment":
                comment_end_line = child.end_point[0]
                if comment_end_line == node_line - 1:
                    return True
        return False

    # ------------------------------------------------------------------
    # Suggestion helpers
    # ------------------------------------------------------------------

    def _suggest_complexity(self, max_cc: int) -> list[str]:
        """Generate complexity improvement suggestions."""
        suggestions: list[str] = []
        if max_cc > 15:
            suggestions.append("Consider breaking down complex functions")
            suggestions.append("Extract conditional logic into separate functions")
        elif max_cc > 10:
            suggestions.append("Consider simplifying control flow")
        return suggestions

    def _suggest_security(self, issues: list[str]) -> list[str]:
        """Generate security improvement suggestions."""
        suggestions: list[str] = []
        for issue in issues:
            if "unsafe" in issue.lower():
                suggestions.append("Avoid unsafe package unless absolutely necessary")
            if "sql" in issue.lower():
                suggestions.append("Use parameterized queries to prevent SQL injection")
            if "exec" in issue.lower():
                suggestions.append("Validate and sanitize inputs before exec")
        return suggestions[:3]

    def _suggest_maintainability(
        self, doc_ratio: float, exported_count: int
    ) -> list[str]:
        """Generate maintainability improvement suggestions."""
        suggestions: list[str] = []
        if doc_ratio < 0.5 and exported_count > 0:
            suggestions.append("Add doc comments to exported functions")
        return suggestions

    def _suggest_performance(self, issues: list[str]) -> list[str]:
        """Generate performance improvement suggestions."""
        suggestions: list[str] = []
        for issue in issues:
            if "defer" in issue.lower():
                suggestions.append("Move defer outside of loops")
            if "goroutine" in issue.lower():
                suggestions.append("Use context for goroutine cancellation")
        return suggestions[:3]

    def _suggest_devex(self, issues: list[str]) -> list[str]:
        """Generate developer experience improvement suggestions."""
        suggestions: list[str] = []
        for issue in issues:
            if "error" in issue.lower():
                suggestions.append("Handle all errors explicitly")
            if "blank" in issue.lower():
                suggestions.append("Avoid discarding values with blank identifier")
            if "snake" in issue.lower():
                suggestions.append("Use MixedCaps naming convention")
        return suggestions
