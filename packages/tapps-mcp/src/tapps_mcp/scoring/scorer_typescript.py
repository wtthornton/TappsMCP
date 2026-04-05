"""TypeScript/JavaScript code scorer.

Scores TypeScript and JavaScript files across quality categories using
tree-sitter parsing for AST-based analysis.

Epic 56: Non-Python Language Scoring
Story 56.3: TypeScript/JavaScript Scorer
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
_TS_LANGUAGE: Any = None
_TSX_LANGUAGE: Any = None
try:
    import tree_sitter
    import tree_sitter_typescript

    _TS_LANGUAGE = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    _TSX_LANGUAGE = tree_sitter.Language(tree_sitter_typescript.language_tsx())
    HAS_TREE_SITTER = True
except ImportError:
    tree_sitter = None  # type: ignore[assignment]
    HAS_TREE_SITTER = False

# Categories supported by the TypeScript scorer
_TYPESCRIPT_CATEGORIES: list[str] = [
    "complexity",
    "security",
    "maintainability",
    "test_coverage",
    "performance",
    "structure",
    "devex",
]

# Security patterns to detect
_SECURITY_PATTERNS: list[tuple[str, str]] = [
    (r"\beval\s*\(", "eval() usage"),
    (r"\.innerHTML\s*=", "innerHTML assignment"),
    (r"dangerouslySetInnerHTML", "dangerouslySetInnerHTML usage"),
    (r"document\.write\s*\(", "document.write() usage"),
    (r"new\s+Function\s*\(", "new Function() usage"),
    (r"setTimeout\s*\(\s*['\"]", "setTimeout with string argument"),
    (r"setInterval\s*\(\s*['\"]", "setInterval with string argument"),
    (r"\.outerHTML\s*=", "outerHTML assignment"),
    (r"__proto__", "__proto__ access"),
    (r"Object\.assign\s*\(\s*\{\}", "prototype pollution risk"),
]

# Performance anti-patterns
_PERFORMANCE_PATTERNS: list[tuple[str, str]] = [
    (r"XMLHttpRequest", "synchronous XHR"),
    (r"\.forEach\s*\([^)]*\.forEach", "nested forEach"),
    (r"JSON\.parse\s*\(\s*JSON\.stringify", "deep clone via JSON"),
]

# Max file size to parse (10 MB)
_MAX_FILE_SIZE = 10 * 1024 * 1024


class TypeScriptScorer(ScorerBase):
    """Score TypeScript and JavaScript files across quality categories.

    This scorer handles .ts, .tsx, .js, .jsx, .mjs, and .cjs files.
    It uses tree-sitter parsing for AST-based analysis when available,
    falling back to regex-based analysis otherwise.

    Categories scored:
    - complexity: Cyclomatic complexity via AST branch counting
    - security: Pattern detection (eval, innerHTML, dangerouslySetInnerHTML)
    - maintainability: JSDoc presence, TypeScript type coverage
    - test_coverage: Test file detection (*.test.ts, *.spec.ts)
    - performance: Nested loops, sync operations
    - structure: Import analysis, nesting depth
    - devex: Naming conventions, `any` type usage
    """

    def __init__(
        self,
        settings: TappsMCPSettings | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        """Initialize the TypeScript scorer."""
        super().__init__(settings, weights)
        self._is_tsx = False

    @property
    def language(self) -> str:
        """Return 'typescript' as the language identifier."""
        return "typescript"

    @property
    def supported_categories(self) -> list[str]:
        """Return the categories supported by this scorer."""
        return _TYPESCRIPT_CATEGORIES.copy()

    @property
    def file_extensions(self) -> frozenset[str]:
        """Return TypeScript and JavaScript file extensions."""
        return frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})

    def score_file_quick(self, file_path: Path) -> ScoreResult:
        """Quick mode scoring for TypeScript/JavaScript files.

        Uses regex-based analysis for fast feedback during edit loops.
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

        # Quick mode: regex-based linting check
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
            language="typescript",
        )

    async def score_file(self, file_path: Path, *, mode: str = "subprocess") -> ScoreResult:
        """Full mode scoring for TypeScript/JavaScript files.

        Uses tree-sitter parsing when available for comprehensive analysis.
        Falls back to regex-based analysis otherwise.

        Args:
            file_path: Path to the file to score.
            mode: Execution mode (currently unused, reserved for future linter integration).

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

        # Detect TSX
        self._is_tsx = resolved.suffix.lower() == ".tsx"

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
            language="typescript",
        )

    # ------------------------------------------------------------------
    # Tree-sitter based scoring
    # ------------------------------------------------------------------

    def _score_with_treesitter(
        self, code: str, file_path: Path
    ) -> dict[str, CategoryScore]:
        """Score using tree-sitter AST analysis."""
        source_bytes = code.encode("utf-8")
        lang = _TSX_LANGUAGE if self._is_tsx else _TS_LANGUAGE
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(source_bytes)
        root = tree.root_node

        w = self._weights
        cats: dict[str, CategoryScore] = {}

        # 1) Complexity
        cats["complexity"] = self._score_complexity_ts(root, source_bytes, w.complexity)

        # 2) Security
        cats["security"] = self._score_security_ts(code, root, source_bytes, w.security)

        # 3) Maintainability
        cats["maintainability"] = self._score_maintainability_ts(
            code, root, source_bytes, w.maintainability
        )

        # 4) Test coverage
        cats["test_coverage"] = self._score_test_coverage_ts(file_path, root, w.test_coverage)

        # 5) Performance
        cats["performance"] = self._score_performance_ts(code, root, source_bytes, w.performance)

        # 6) Structure
        cats["structure"] = self._score_structure_ts(root, source_bytes, file_path, w.structure)

        # 7) DevEx
        cats["devex"] = self._score_devex_ts(code, root, source_bytes, w.devex)

        return cats

    def _score_complexity_ts(
        self, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate complexity score via AST branch counting."""
        # Count branching nodes for cyclomatic complexity
        branch_types = {
            "if_statement",
            "for_statement",
            "for_in_statement",
            "while_statement",
            "do_statement",
            "switch_case",
            "catch_clause",
            "ternary_expression",
            "binary_expression",  # && and || contribute to complexity
        }

        function_complexities: list[int] = []

        def count_branches(node: Any) -> int:
            """Count branches in a node recursively."""
            count = 0
            if node.type in branch_types:
                # For binary expressions, only count && and ||
                if node.type == "binary_expression":
                    op_node = node.child_by_field_name("operator")
                    if op_node:
                        op = source[op_node.start_byte:op_node.end_byte].decode()
                        if op in ("&&", "||", "??"):
                            count = 1
                else:
                    count = 1
            for child in node.children:
                count += count_branches(child)
            return count

        # Find all functions and calculate their complexity
        for node in self._walk_tree(root):
            if node.type in (
                "function_declaration",
                "function",
                "arrow_function",
                "method_definition",
            ):
                cc = 1 + count_branches(node)
                function_complexities.append(cc)

        if function_complexities:
            max_cc = max(function_complexities)
            avg_cc = sum(function_complexities) / len(function_complexities)
        else:
            max_cc = 1 + count_branches(root)
            avg_cc = max_cc

        # Score: lower complexity is better (inverted in overall calculation)
        # Score 1-10 where higher score = higher complexity
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

    def _score_security_ts(
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
            # Detect eval() calls
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node:
                    func_text = source[func_node.start_byte:func_node.end_byte].decode()
                    if func_text == "eval" and "eval() usage" not in issues_found:
                        issues_found.append("eval() usage")

        penalty = len(issues_found) * 2.0
        score = clamp_individual(10.0 - penalty)

        return CategoryScore(
            name="security",
            score=score,
            weight=weight,
            details={"issues_found": issues_found, "issue_count": len(issues_found)},
            suggestions=self._suggest_security(issues_found),
        )

    def _score_maintainability_ts(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate maintainability score."""
        lines = code.splitlines()
        line_count = len(lines)

        # Check for JSDoc comments
        jsdoc_count = len(re.findall(r"/\*\*[\s\S]*?\*/", code))
        has_jsdoc = jsdoc_count > 0

        # Count functions to calculate documentation ratio
        function_count = 0
        for node in self._walk_tree(root):
            if node.type in (
                "function_declaration",
                "function",
                "arrow_function",
                "method_definition",
            ):
                function_count += 1

        doc_ratio = jsdoc_count / max(function_count, 1)

        # Start with base score
        score = 8.0

        # Penalize for large files
        if line_count > 500:
            score -= 2.0
        elif line_count > 300:
            score -= 1.0

        # Reward for documentation
        if doc_ratio >= 0.5:
            score += 1.0
        elif not has_jsdoc:
            score -= 1.0

        score = clamp_individual(score)

        return CategoryScore(
            name="maintainability",
            score=score,
            weight=weight,
            details={
                "line_count": line_count,
                "jsdoc_count": jsdoc_count,
                "function_count": function_count,
                "doc_ratio": round(doc_ratio, 2),
            },
            suggestions=self._suggest_maintainability(line_count, has_jsdoc, doc_ratio),
        )

    def _score_test_coverage_ts(
        self, file_path: Path, root: Any, weight: float
    ) -> CategoryScore:
        """Calculate test coverage heuristic score."""
        name = file_path.name.lower()
        stem = file_path.stem.lower()

        # Check if this is a test file
        is_test_file = any([
            name.endswith(".test.ts"),
            name.endswith(".test.tsx"),
            name.endswith(".test.js"),
            name.endswith(".test.jsx"),
            name.endswith(".spec.ts"),
            name.endswith(".spec.tsx"),
            name.endswith(".spec.js"),
            name.endswith(".spec.jsx"),
            stem.startswith("test_"),
            stem.endswith("_test"),
        ])

        if is_test_file:
            score = 5.0  # Neutral for test files
        else:
            # Check if corresponding test file might exist
            test_dir = file_path.parent
            possible_tests = [
                test_dir / f"{file_path.stem}.test{file_path.suffix}",
                test_dir / f"{file_path.stem}.spec{file_path.suffix}",
                test_dir / "__tests__" / f"{file_path.stem}.test{file_path.suffix}",
                test_dir.parent / "tests" / f"{file_path.stem}.test{file_path.suffix}",
            ]
            has_test = any(p.exists() for p in possible_tests)
            score = 5.0 if has_test else 0.0

        return CategoryScore(
            name="test_coverage",
            score=score,
            weight=weight,
            details={"is_test_file": is_test_file},
            suggestions=[] if is_test_file or score > 0 else ["Consider adding tests"],
        )

    def _score_performance_ts(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate performance score via pattern detection."""
        issues_found: list[str] = []

        # Regex-based detection
        for pattern, description in _PERFORMANCE_PATTERNS:
            if re.search(pattern, code):
                issues_found.append(description)

        # AST-based detection for nested loops
        for node in self._walk_tree(root):
            if node.type in ("for_statement", "for_in_statement", "while_statement"):
                # Check for nested loops
                for child in self._walk_tree(node):
                    if child is not node and child.type in (
                        "for_statement",
                        "for_in_statement",
                        "while_statement",
                    ):
                        if "nested loops" not in issues_found:
                            issues_found.append("nested loops")
                        break

        penalty = len(issues_found) * 1.5
        score = clamp_individual(10.0 - penalty)

        return CategoryScore(
            name="performance",
            score=score,
            weight=weight,
            details={"issues_found": issues_found},
            suggestions=self._suggest_performance(issues_found),
        )

    def _score_structure_ts(
        self, root: Any, source: bytes, file_path: Path, weight: float
    ) -> CategoryScore:
        """Calculate structure score."""
        # Count imports
        import_count = 0
        for node in root.children:
            if node.type == "import_statement":
                import_count += 1

        # Check nesting depth
        max_depth = self._max_nesting_depth(root)

        # Start with base score
        score = 8.0

        # Penalize for excessive imports
        if import_count > 30:
            score -= 2.0
        elif import_count > 20:
            score -= 1.0

        # Penalize for deep nesting
        if max_depth > 6:
            score -= 2.0
        elif max_depth > 4:
            score -= 1.0

        # Bonus for being in a well-structured project
        if (file_path.parent / "package.json").exists():
            score += 0.5
        if (file_path.parent / "tsconfig.json").exists():
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

    def _score_devex_ts(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate developer experience score."""
        issues: list[str] = []

        # Count `any` type usage
        any_count = len(re.findall(r":\s*any\b", code))
        if any_count > 5:
            issues.append(f"excessive 'any' usage ({any_count} occurrences)")
        elif any_count > 0:
            issues.append(f"'any' type usage ({any_count} occurrences)")

        # Check for type annotations in function parameters
        typed_params = len(re.findall(r"\([^)]*:\s*\w+", code))
        untyped_params = len(re.findall(r"\(\s*\w+\s*[,)]", code))

        type_coverage = typed_params / max(typed_params + untyped_params, 1)

        # Check naming conventions (camelCase for functions/variables)
        # This is a heuristic - count PascalCase that isn't a class/type
        snake_case_vars = len(re.findall(r"\b[a-z]+_[a-z]+\b", code))
        if snake_case_vars > 5:
            issues.append("inconsistent naming (snake_case detected)")

        score = 8.0
        if any_count > 5:
            score -= 2.0
        elif any_count > 0:
            score -= 0.5 * any_count

        if type_coverage < 0.5:
            score -= 1.0

        if snake_case_vars > 5:
            score -= 0.5

        score = clamp_individual(score)

        return CategoryScore(
            name="devex",
            score=score,
            weight=weight,
            details={
                "any_count": any_count,
                "type_coverage": round(type_coverage, 2),
                "issues": issues,
            },
            suggestions=self._suggest_devex(any_count, type_coverage),
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
            len(re.findall(r"\bif\s*\(", code)),
            len(re.findall(r"\bfor\s*\(", code)),
            len(re.findall(r"\bwhile\s*\(", code)),
            len(re.findall(r"\bswitch\s*\(", code)),
            len(re.findall(r"\?\s*[^:]+\s*:", code)),  # ternary
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
        jsdoc_count = len(re.findall(r"/\*\*[\s\S]*?\*/", code))
        maint_score = 8.0
        if line_count > 500:
            maint_score -= 2.0
        elif line_count > 300:
            maint_score -= 1.0
        if jsdoc_count == 0:
            maint_score -= 1.0
        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=clamp_individual(maint_score),
            weight=w.maintainability,
            details={"line_count": line_count, "jsdoc_count": jsdoc_count, "fallback": True},
        )

        # 4) Test coverage
        name = file_path.name.lower()
        is_test = any([
            ".test." in name,
            ".spec." in name,
            name.startswith("test_"),
        ])
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
        import_count = len(re.findall(r"^import\s+", code, re.MULTILINE))
        struct_score = 8.0
        if import_count > 30:
            struct_score -= 2.0
        elif import_count > 20:
            struct_score -= 1.0
        cats["structure"] = CategoryScore(
            name="structure",
            score=clamp_individual(struct_score),
            weight=w.structure,
            details={"import_count": import_count, "fallback": True},
        )

        # 7) DevEx
        any_count = len(re.findall(r":\s*any\b", code))
        devex_score = 8.0 - min(any_count * 0.5, 3.0)
        cats["devex"] = CategoryScore(
            name="devex",
            score=clamp_individual(devex_score),
            weight=w.devex,
            details={"any_count": any_count, "fallback": True},
        )

        return cats

    def _regex_lint_check(self, code: str) -> list[str]:
        """Quick regex-based lint check for common issues."""
        issues: list[str] = []

        # Check for console.log
        if re.search(r"console\.(log|debug|info)\s*\(", code):
            issues.append("console.log statement found")

        # Check for debugger
        if re.search(r"\bdebugger\b", code):
            issues.append("debugger statement found")

        # Check for TODO/FIXME
        if re.search(r"//\s*(TODO|FIXME|XXX|HACK)\b", code, re.IGNORECASE):
            issues.append("TODO/FIXME comment found")

        # Check for `any` type
        any_count = len(re.findall(r":\s*any\b", code))
        if any_count > 0:
            issues.append(f"'any' type used {any_count} times")

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
            "for_in_statement",
            "while_statement",
            "do_statement",
            "switch_statement",
            "try_statement",
        }
        max_d = depth
        for child in node.children:
            if child.type in control_types:
                max_d = max(max_d, self._max_nesting_depth(child, depth + 1))
            else:
                max_d = max(max_d, self._max_nesting_depth(child, depth))
        return max_d

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
            if "eval" in issue:
                suggestions.append("Replace eval() with safer alternatives")
            if "innerHTML" in issue:
                suggestions.append("Use textContent or sanitize HTML input")
            if "dangerouslySetInnerHTML" in issue:
                suggestions.append("Sanitize content before using dangerouslySetInnerHTML")
        return suggestions[:3]

    def _suggest_maintainability(
        self, line_count: int, has_jsdoc: bool, doc_ratio: float
    ) -> list[str]:
        """Generate maintainability improvement suggestions."""
        suggestions: list[str] = []
        if line_count > 500:
            suggestions.append("Consider splitting this file into smaller modules")
        if not has_jsdoc:
            suggestions.append("Add JSDoc comments to public functions")
        elif doc_ratio < 0.5:
            suggestions.append("Improve documentation coverage")
        return suggestions

    def _suggest_performance(self, issues: list[str]) -> list[str]:
        """Generate performance improvement suggestions."""
        suggestions: list[str] = []
        for issue in issues:
            if "nested" in issue.lower():
                suggestions.append("Consider using Map or Set to avoid nested iterations")
            if "JSON" in issue:
                suggestions.append("Use structuredClone() for deep cloning")
        return suggestions[:3]

    def _suggest_devex(self, any_count: int, type_coverage: float) -> list[str]:
        """Generate developer experience improvement suggestions."""
        suggestions: list[str] = []
        if any_count > 0:
            suggestions.append("Replace 'any' with specific types")
        if type_coverage < 0.5:
            suggestions.append("Add type annotations to improve type safety")
        return suggestions
