"""Rust code scorer.

Scores Rust files across quality categories using tree-sitter parsing
for AST-based analysis.

Epic 56: Non-Python Language Scoring
Story 56.5: Rust Scorer
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
_RUST_LANGUAGE: Any = None
try:
    import tree_sitter
    import tree_sitter_rust

    _RUST_LANGUAGE = tree_sitter.Language(tree_sitter_rust.language())
    HAS_TREE_SITTER = True
except ImportError:
    tree_sitter = None  # type: ignore[assignment]
    HAS_TREE_SITTER = False

# Categories supported by the Rust scorer
_RUST_CATEGORIES: list[str] = [
    "complexity",
    "security",
    "maintainability",
    "test_coverage",
    "performance",
    "structure",
    "devex",
]

# Security patterns to detect in Rust code
_SECURITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bunsafe\s*\{", "unsafe block"),
    (r"std::mem::transmute", "transmute usage"),
    (r"std::ptr::read", "raw pointer read"),
    (r"std::ptr::write", "raw pointer write"),
    (r"#\[allow\(unsafe_code\)\]", "unsafe_code allowed"),
    (r"Box::leak", "Box::leak (memory leak)"),
    (r"std::mem::forget", "mem::forget (resource leak)"),
    (r"as\s+\*const|\*mut", "raw pointer cast"),
]

# Performance anti-patterns
_PERFORMANCE_PATTERNS: list[tuple[str, str]] = [
    (r"\.clone\(\)\s*\)", "clone() in hot path"),
    (r"\.to_string\(\)\s*\)", "to_string() allocation"),
    (r"\.collect::<Vec<", "unnecessary collect"),
    (r"format!\s*\([^)]*\)\s*\.as_str\(\)", "format! then as_str"),
]

# Max file size to parse (10 MB)
_MAX_FILE_SIZE = 10 * 1024 * 1024


class RustScorer(ScorerBase):
    """Score Rust files across quality categories.

    This scorer handles .rs files. It uses tree-sitter parsing
    for AST-based analysis when available.

    Categories scored:
    - complexity: Cyclomatic complexity via AST branch counting
    - security: Pattern detection (unsafe blocks, .unwrap() abuse)
    - maintainability: Doc comments (///), type annotations
    - test_coverage: #[test] attributes, #[cfg(test)] modules
    - performance: .clone() in loops, needless allocations
    - structure: use statements, module nesting
    - devex: Naming conventions (snake_case), unsafe blocks
    """

    def __init__(
        self,
        settings: TappsMCPSettings | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        """Initialize the Rust scorer."""
        super().__init__(settings, weights)

    @property
    def language(self) -> str:
        """Return 'rust' as the language identifier."""
        return "rust"

    @property
    def supported_categories(self) -> list[str]:
        """Return the categories supported by this scorer."""
        return _RUST_CATEGORIES.copy()

    @property
    def file_extensions(self) -> frozenset[str]:
        """Return Rust file extensions."""
        return frozenset({".rs"})

    def score_file_quick(self, file_path: Path) -> ScoreResult:
        """Quick mode scoring for Rust files.

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
            language="rust",
        )

    async def score_file(self, file_path: Path, *, mode: str = "subprocess") -> ScoreResult:
        """Full mode scoring for Rust files.

        Uses tree-sitter parsing when available for comprehensive analysis.

        Args:
            file_path: Path to the file to score.
            mode: Execution mode (reserved for future clippy integration).

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
            language="rust",
        )

    # ------------------------------------------------------------------
    # Tree-sitter based scoring
    # ------------------------------------------------------------------

    def _score_with_treesitter(
        self, code: str, file_path: Path
    ) -> dict[str, CategoryScore]:
        """Score using tree-sitter AST analysis."""
        source_bytes = code.encode("utf-8")
        parser = tree_sitter.Parser(_RUST_LANGUAGE)
        tree = parser.parse(source_bytes)
        root = tree.root_node

        w = self._weights
        cats: dict[str, CategoryScore] = {}

        # 1) Complexity
        cats["complexity"] = self._score_complexity_rs(root, source_bytes, w.complexity)

        # 2) Security
        cats["security"] = self._score_security_rs(code, root, source_bytes, w.security)

        # 3) Maintainability
        cats["maintainability"] = self._score_maintainability_rs(
            code, root, source_bytes, w.maintainability
        )

        # 4) Test coverage
        cats["test_coverage"] = self._score_test_coverage_rs(
            file_path, code, root, source_bytes, w.test_coverage
        )

        # 5) Performance
        cats["performance"] = self._score_performance_rs(code, root, source_bytes, w.performance)

        # 6) Structure
        cats["structure"] = self._score_structure_rs(root, source_bytes, file_path, w.structure)

        # 7) DevEx
        cats["devex"] = self._score_devex_rs(code, root, source_bytes, w.devex)

        return cats

    def _score_complexity_rs(
        self, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate complexity score via AST branch counting."""
        branch_types = {
            "if_expression",
            "if_let_expression",
            "for_expression",
            "while_expression",
            "while_let_expression",
            "loop_expression",
            "match_arm",
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
                    if hasattr(child, "type") and child.type in ("&&", "||"):
                        count += 1
            for child in node.children:
                count += count_branches(child)
            return count

        # Find all functions and calculate their complexity
        for node in self._walk_tree(root):
            if node.type == "function_item":
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

    def _score_security_rs(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate security score via pattern detection."""
        issues_found: list[str] = []

        # Regex-based pattern detection
        for pattern, description in _SECURITY_PATTERNS:
            if re.search(pattern, code):
                issues_found.append(description)

        # AST-based detection
        unsafe_block_count = 0
        unwrap_count = 0

        for node in self._walk_tree(root):
            # Count unsafe blocks
            if node.type == "unsafe_block":
                unsafe_block_count += 1

            # Count .unwrap() calls
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node and func_node.type == "field_expression":
                    field_node = func_node.child_by_field_name("field")
                    if field_node:
                        field_text = source[field_node.start_byte:field_node.end_byte].decode()
                        if field_text == "unwrap":
                            unwrap_count += 1

        if unsafe_block_count > 0 and "unsafe block" not in issues_found:
            issues_found.append(f"unsafe blocks ({unsafe_block_count})")

        if unwrap_count > 3:
            issues_found.append(f"excessive .unwrap() usage ({unwrap_count})")

        penalty = len(issues_found) * 1.5 + unsafe_block_count * 0.5
        score = clamp_individual(10.0 - penalty)

        return CategoryScore(
            name="security",
            score=score,
            weight=weight,
            details={
                "issues_found": issues_found,
                "unsafe_block_count": unsafe_block_count,
                "unwrap_count": unwrap_count,
            },
            suggestions=self._suggest_security(issues_found, unwrap_count),
        )

    def _score_maintainability_rs(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate maintainability score."""
        lines = code.splitlines()
        line_count = len(lines)

        # Count doc comments (/// style)
        doc_comment_count = len(re.findall(r"^\s*///", code, re.MULTILINE))

        # Count public items
        pub_count = 0
        documented_pub = 0

        for node in self._walk_tree(root):
            if node.type in ("function_item", "struct_item", "enum_item", "trait_item"):
                # Check for pub visibility
                is_pub = False
                for child in node.children:
                    if child.type == "visibility_modifier":
                        is_pub = True
                        break

                if is_pub:
                    pub_count += 1
                    # Check for doc comment before
                    if self._has_doc_comment(node, source):
                        documented_pub += 1

        doc_ratio = documented_pub / max(pub_count, 1)

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
        elif doc_ratio < 0.5 and pub_count > 0:
            score -= 1.0

        score = clamp_individual(score)

        return CategoryScore(
            name="maintainability",
            score=score,
            weight=weight,
            details={
                "line_count": line_count,
                "pub_count": pub_count,
                "documented_pub": documented_pub,
                "doc_ratio": round(doc_ratio, 2),
                "doc_comment_count": doc_comment_count,
            },
            suggestions=self._suggest_maintainability(doc_ratio, pub_count),
        )

    def _score_test_coverage_rs(
        self, file_path: Path, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate test coverage heuristic score."""
        # Check for #[test] attributes
        test_count = len(re.findall(r"#\[test\]", code))

        # Check for #[cfg(test)] module
        has_test_module = bool(re.search(r"#\[cfg\(test\)\]", code))

        # Check if this is in a tests directory
        is_in_tests = "tests" in file_path.parts or "test" in file_path.parts

        if test_count > 0 or has_test_module or is_in_tests:
            score = 5.0  # Neutral for test files
            is_test_file = True
        else:
            # Check if corresponding test exists
            test_paths = [
                file_path.parent / "tests" / f"{file_path.stem}_test.rs",
                file_path.parent.parent / "tests" / f"{file_path.stem}.rs",
            ]
            has_test = any(p.exists() for p in test_paths)
            score = 5.0 if has_test else 0.0
            is_test_file = False

        return CategoryScore(
            name="test_coverage",
            score=score,
            weight=weight,
            details={
                "test_count": test_count,
                "has_test_module": has_test_module,
                "is_test_file": is_test_file,
            },
            suggestions=[] if score > 0 else ["Consider adding tests with #[test]"],
        )

    def _score_performance_rs(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate performance score via pattern detection."""
        issues_found: list[str] = []

        # Regex-based detection
        for pattern, description in _PERFORMANCE_PATTERNS:
            if re.search(pattern, code):
                issues_found.append(description)

        # AST-based detection for clone() in loops
        for node in self._walk_tree(root):
            if node.type in ("for_expression", "while_expression", "loop_expression"):
                for child in self._walk_tree(node):
                    if child.type == "call_expression":
                        func_node = child.child_by_field_name("function")
                        if func_node and func_node.type == "field_expression":
                            field = func_node.child_by_field_name("field")
                            if field:
                                text = source[field.start_byte:field.end_byte].decode()
                                if text == "clone":
                                    if "clone() in loop" not in issues_found:
                                        issues_found.append("clone() in loop")
                                    break

        # Check for Box::new in loops (allocation in hot path)
        box_in_loop = len(re.findall(r"for\s+.*\{[^}]*Box::new", code, re.DOTALL))
        if box_in_loop > 0:
            issues_found.append("Box::new in loop (allocation in hot path)")

        penalty = len(issues_found) * 1.5
        score = clamp_individual(10.0 - penalty)

        return CategoryScore(
            name="performance",
            score=score,
            weight=weight,
            details={"issues_found": issues_found},
            suggestions=self._suggest_performance(issues_found),
        )

    def _score_structure_rs(
        self, root: Any, source: bytes, file_path: Path, weight: float
    ) -> CategoryScore:
        """Calculate structure score."""
        # Count use statements
        use_count = 0
        for node in root.children:
            if node.type == "use_declaration":
                use_count += 1

        # Check nesting depth
        max_depth = self._max_nesting_depth(root)

        # Check module organization
        mod_count = len(re.findall(r"\bmod\s+\w+", source.decode("utf-8", errors="replace")))

        # Start with base score
        score = 8.0

        # Penalize for excessive use statements
        if use_count > 25:
            score -= 2.0
        elif use_count > 15:
            score -= 1.0

        # Penalize for deep nesting
        if max_depth > 5:
            score -= 2.0
        elif max_depth > 4:
            score -= 1.0

        # Bonus for being in a well-structured project
        if (file_path.parent / "Cargo.toml").exists():
            score += 0.5
        if (file_path.parent / "src").exists() or file_path.parent.name == "src":
            score += 0.5

        score = clamp_individual(score)

        return CategoryScore(
            name="structure",
            score=score,
            weight=weight,
            details={
                "use_count": use_count,
                "mod_count": mod_count,
                "max_nesting_depth": max_depth,
            },
        )

    def _score_devex_rs(
        self, code: str, root: Any, source: bytes, weight: float
    ) -> CategoryScore:
        """Calculate developer experience score."""
        issues: list[str] = []

        # Check for unwrap() usage (prefer expect() or ? operator)
        unwrap_count = len(re.findall(r"\.unwrap\(\)", code))
        expect_count = len(re.findall(r"\.expect\(", code))
        question_mark = len(re.findall(r"\?;|\?\s*$|\?\s*\}", code, re.MULTILINE))

        if unwrap_count > expect_count + question_mark:
            issues.append("prefer expect() or ? over unwrap()")

        # Check naming conventions (Rust uses snake_case)
        camel_case_fns = len(re.findall(r"\bfn\s+[a-z]+[A-Z]", code))
        if camel_case_fns > 0:
            issues.append("use snake_case for function names")

        # Check for excessive use of derive macros
        derive_count = len(re.findall(r"#\[derive\([^\)]+\)\]", code))
        if derive_count > 10:
            issues.append(f"many derive macros ({derive_count}) - consider if all needed")

        # Check for clippy allows
        clippy_allows = len(re.findall(r"#\[allow\(clippy::", code))
        if clippy_allows > 3:
            issues.append(f"multiple clippy lints suppressed ({clippy_allows})")

        score = 8.0
        if issues:
            score -= len(issues) * 0.5

        score = clamp_individual(score)

        return CategoryScore(
            name="devex",
            score=score,
            weight=weight,
            details={
                "unwrap_count": unwrap_count,
                "expect_count": expect_count,
                "question_mark_count": question_mark,
                "issues": issues,
            },
            suggestions=self._suggest_devex(issues, unwrap_count),
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
            len(re.findall(r"\bwhile\s+", code)),
            len(re.findall(r"\bmatch\s+", code)),
            len(re.findall(r"\bloop\s*\{", code)),
            len(re.findall(r"=>\s*\{", code)),  # match arms
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
        unwrap_count = len(re.findall(r"\.unwrap\(\)", code))
        if unwrap_count > 5:
            security_issues.append(f"excessive .unwrap() ({unwrap_count})")
        security_score = clamp_individual(10.0 - len(security_issues) * 1.5)
        cats["security"] = CategoryScore(
            name="security",
            score=security_score,
            weight=w.security,
            details={"issues_found": security_issues, "fallback": True},
        )

        # 3) Maintainability
        doc_comments = len(re.findall(r"^\s*///", code, re.MULTILINE))
        maint_score = 8.0
        if line_count > 500:
            maint_score -= 2.0
        elif line_count > 300:
            maint_score -= 1.0
        if doc_comments < 3:
            maint_score -= 1.0
        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=clamp_individual(maint_score),
            weight=w.maintainability,
            details={"line_count": line_count, "doc_comments": doc_comments, "fallback": True},
        )

        # 4) Test coverage
        test_count = len(re.findall(r"#\[test\]", code))
        has_test_module = bool(re.search(r"#\[cfg\(test\)\]", code))
        cats["test_coverage"] = CategoryScore(
            name="test_coverage",
            score=5.0 if test_count > 0 or has_test_module else 0.0,
            weight=w.test_coverage,
            details={"test_count": test_count, "has_test_module": has_test_module, "fallback": True},
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
        use_count = len(re.findall(r"^\s*use\s+", code, re.MULTILINE))
        struct_score = 8.0
        if use_count > 25:
            struct_score -= 2.0
        elif use_count > 15:
            struct_score -= 1.0
        cats["structure"] = CategoryScore(
            name="structure",
            score=clamp_individual(struct_score),
            weight=w.structure,
            details={"use_count": use_count, "fallback": True},
        )

        # 7) DevEx
        devex_score = 8.0
        if unwrap_count > 5:
            devex_score -= 1.0
        cats["devex"] = CategoryScore(
            name="devex",
            score=clamp_individual(devex_score),
            weight=w.devex,
            details={"unwrap_count": unwrap_count, "fallback": True},
        )

        return cats

    def _regex_lint_check(self, code: str) -> list[str]:
        """Quick regex-based lint check for common issues."""
        issues: list[str] = []

        # Check for println! (should use log or tracing)
        if re.search(r"println!\s*\(", code):
            issues.append("println! found (consider tracing/log)")

        # Check for dbg!
        if re.search(r"dbg!\s*\(", code):
            issues.append("dbg! macro found")

        # Check for TODO/FIXME
        if re.search(r"//\s*(TODO|FIXME|XXX|HACK)\b", code, re.IGNORECASE):
            issues.append("TODO/FIXME comment found")

        # Check for unsafe
        unsafe_count = len(re.findall(r"\bunsafe\s*\{", code))
        if unsafe_count > 0:
            issues.append(f"unsafe blocks found ({unsafe_count})")

        # Check for unwrap
        unwrap_count = len(re.findall(r"\.unwrap\(\)", code))
        if unwrap_count > 3:
            issues.append(f".unwrap() used {unwrap_count} times")

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
            "if_expression",
            "if_let_expression",
            "for_expression",
            "while_expression",
            "while_let_expression",
            "loop_expression",
            "match_expression",
        }
        max_d = depth
        for child in node.children:
            if child.type in control_types:
                max_d = max(max_d, self._max_nesting_depth(child, depth + 1))
            else:
                max_d = max(max_d, self._max_nesting_depth(child, depth))
        return max_d

    def _has_doc_comment(self, node: Any, source: bytes) -> bool:
        """Check if a node has a doc comment (///) preceding it."""
        # Look at the source before the node
        node_start = node.start_byte
        if node_start < 4:
            return False
        # Get content before node
        before = source[:node_start].decode("utf-8", errors="replace")
        lines = before.rstrip().split("\n")
        if lines:
            last_line = lines[-1].strip()
            return last_line.startswith("///")
        return False

    # ------------------------------------------------------------------
    # Suggestion helpers
    # ------------------------------------------------------------------

    def _suggest_complexity(self, max_cc: int) -> list[str]:
        """Generate complexity improvement suggestions."""
        suggestions: list[str] = []
        if max_cc > 15:
            suggestions.append("Consider breaking down complex functions")
            suggestions.append("Extract match arms into separate functions")
        elif max_cc > 10:
            suggestions.append("Consider simplifying control flow")
        return suggestions

    def _suggest_security(self, issues: list[str], unwrap_count: int) -> list[str]:
        """Generate security improvement suggestions."""
        suggestions: list[str] = []
        if unwrap_count > 3:
            suggestions.append("Replace .unwrap() with .expect() or ? operator")
        for issue in issues:
            if "unsafe" in issue.lower():
                suggestions.append("Document why unsafe is needed, minimize unsafe scope")
            if "transmute" in issue.lower():
                suggestions.append("Avoid transmute - use safer alternatives")
        return suggestions[:3]

    def _suggest_maintainability(
        self, doc_ratio: float, pub_count: int
    ) -> list[str]:
        """Generate maintainability improvement suggestions."""
        suggestions: list[str] = []
        if doc_ratio < 0.5 and pub_count > 0:
            suggestions.append("Add /// doc comments to public items")
        return suggestions

    def _suggest_performance(self, issues: list[str]) -> list[str]:
        """Generate performance improvement suggestions."""
        suggestions: list[str] = []
        for issue in issues:
            if "clone" in issue.lower():
                suggestions.append("Consider borrowing instead of cloning")
            if "collect" in issue.lower():
                suggestions.append("Use iterators directly when possible")
            if "Box::new" in issue:
                suggestions.append("Pre-allocate outside loops")
        return suggestions[:3]

    def _suggest_devex(self, issues: list[str], unwrap_count: int) -> list[str]:
        """Generate developer experience improvement suggestions."""
        suggestions: list[str] = []
        if unwrap_count > 3:
            suggestions.append("Use ? operator for error propagation")
            suggestions.append("Use .expect('reason') for panics that should never happen")
        for issue in issues:
            if "snake_case" in issue:
                suggestions.append("Rust convention: use snake_case for functions/variables")
        return suggestions
