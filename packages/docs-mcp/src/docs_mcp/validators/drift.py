"""Drift detection: identify code changes not reflected in documentation."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from docs_mcp.analyzers.api_surface import APISurface

logger = structlog.get_logger(__name__)

# Directories to skip when scanning for Python source files (extends shared constants).
from docs_mcp.constants import SKIP_DIRS as _BASE_SKIP_DIRS

_SKIP_DIRS: frozenset[str] = _BASE_SKIP_DIRS | frozenset({".hg", ".svn", ".env"})

# Documentation file extensions to scan for references.
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# Minimum token length for fuzzy matching (shorter tokens produce too many false matches,
# e.g. "T" from "TypeVar" would match stray T characters in prose).
_MIN_FUZZY_TOKEN_LEN: int = 4

# Default ignore patterns for fully-qualified symbol names. Opt-in via
# ``ignore_patterns="defaults"`` on ``DriftDetector.check`` — never applied implicitly
# to avoid surprising existing callers.
_DEFAULT_IGNORE_PATTERNS: list[str] = [
    "_*",
    "test_*",
    "tests.*",
    "*._*",
]

# Camel/Pascal case splitter. Emits each "word" piece, keeping contiguous digits
# glued to the preceding letter run so "BM25Scorer" -> ["BM25", "Scorer"].
# Alternatives (left-to-right, greedy):
#   * Acronym-then-word:   BM25Scorer has "BM" before "Scorer"  -> match "BM"
#     captured by the acronym+lookahead case, digits captured separately.
#   * Letters+digits run:  "BM25", "HTTP2"                      -> one token.
#   * CamelCase word:      "Scorer", "Reranker"                 -> one token.
#   * Lowercase word:      "user", "bm25scorer"                 -> one token.
_CAMEL_SPLIT_RE = re.compile(
    r"[A-Z]+[0-9]+|"  # letters+digits run, e.g. BM25, HTTP2
    r"[A-Z][a-z0-9]+|"  # CamelCase word
    r"[A-Z]+(?=[A-Z])|"  # leading all-caps before next capitalised word
    r"[A-Z]+|"  # trailing all-caps acronym
    r"[a-z0-9]+"  # lowercase word
)


class DriftItem(BaseModel):
    """A single drift finding between code and documentation."""

    file_path: str
    drift_type: str  # "added_undocumented", "modified_undocumented", "removed_stale"
    severity: str = "warning"  # "warning", "error"
    description: str = ""
    symbols: list[str] = []  # full list of undocumented public names (not truncated)
    code_last_modified: str = ""  # ISO date
    doc_last_modified: str = ""  # ISO date


class DriftReport(BaseModel):
    """Aggregated drift detection results.

    ``drift_score`` is on a 0-100 scale (0 = no drift, 100 = severe drift) to match
    sibling validators such as ``FreshnessReport.freshness_score``. The underlying
    0.0-1.0 fraction is preserved in ``drift_fraction`` for callers that want the raw
    ratio.
    """

    total_items: int = 0
    items: list[DriftItem] = []
    drift_score: float = 0.0  # 0-100 (0 = no drift, 100 = severe drift)
    drift_fraction: float = 0.0  # 0.0-1.0 internal fraction (drifted files / checked)
    checked_files: int = 0


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    if dirname in _SKIP_DIRS:
        return True
    return dirname.endswith(".egg-info")


def _iso_from_mtime(mtime: float) -> str:
    """Convert a file modification time to an ISO date string (UTC)."""
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))


def _find_python_files(project_root: Path) -> list[Path]:
    """Find all Python files under the project root."""
    py_files: list[Path] = []
    if not project_root.is_dir():
        return py_files

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        current = Path(dirpath)
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(current / fname)
    return py_files


def _find_doc_files(
    project_root: Path,
    doc_dirs: list[str] | None = None,
) -> list[Path]:
    """Find all documentation files under the project root or specified dirs."""
    doc_files: list[Path] = []

    if doc_dirs:
        # Only scan specified directories
        for ddir in doc_dirs:
            search_root = project_root / ddir
            if not search_root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(search_root):
                dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
                current = Path(dirpath)
                for fname in filenames:
                    fpath = current / fname
                    if fpath.suffix.lower() in _DOC_EXTENSIONS:
                        doc_files.append(fpath)
    else:
        # Scan entire project for doc files (also grab root-level docs)
        if not project_root.is_dir():
            return doc_files
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            current = Path(dirpath)
            for fname in filenames:
                fpath = current / fname
                if fpath.suffix.lower() in _DOC_EXTENSIONS:
                    doc_files.append(fpath)

    return doc_files


def _read_doc_content(doc_files: list[Path]) -> str:
    """Read and concatenate content from all documentation files."""
    parts: list[str] = []
    for fp in doc_files:
        try:
            parts.append(fp.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def _build_doc_word_set(doc_files: list[Path]) -> frozenset[str]:
    """Build an inverted word-set from all documentation files.

    Reads each doc file once and tokenizes its content into a frozenset of lowercase
    words (``\\w+`` tokens). Used by :func:`_name_covered_by_word_set` for O(1)
    membership lookups instead of O(n) substring scans on a concatenated string.
    """
    words: set[str] = set()
    for fp in doc_files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        words.update(re.findall(r"\w+", text.lower()))
    return frozenset(words)


def _build_doc_token_mtime_map(doc_files: list[Path]) -> dict[str, float]:
    """Build a word → max_mtime map from all documentation files.

    For each word in the documentation, records the maximum mtime across all doc files
    that contain it. Combines the word-set lookup (TAP-1121) with per-file mtime
    precision (TAP-1123): the map keys serve as the word index for O(1) coverage
    checks, and the values enable per-code-file severity assessment.
    """
    token_mtime: dict[str, float] = {}
    for fp in doc_files:
        try:
            mtime = fp.stat().st_mtime
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for word in re.findall(r"\w+", text.lower()):
            existing = token_mtime.get(word, 0.0)
            if mtime > existing:
                token_mtime[word] = mtime
    return token_mtime


def _get_relevant_doc_mtime(names: list[str], token_mtime_map: dict[str, float]) -> float:
    """Return the max mtime of doc files mentioning any token of any name.

    For a code file's public API names, finds the most-recently-updated doc file
    that contains any component token. Returns 0.0 if no doc file covers any token,
    which causes the caller to fall back to the global doc mtime.
    """
    best: float = 0.0
    for name in names:
        for token in _tokenize_name(name):
            if len(token) < _MIN_FUZZY_TOKEN_LEN:
                continue
            mtime = token_mtime_map.get(token.lower(), 0.0)
            if mtime > best:
                best = mtime
    return best


def _name_covered_by_word_set(name: str, word_set: frozenset[str]) -> bool:
    """Return True if ``name`` or any long-enough token appears in *word_set*.

    Uses O(1) set membership instead of the O(n) substring scan in
    :func:`_name_covered_by_prose`. Matching is case-insensitive. Tokens shorter
    than :data:`_MIN_FUZZY_TOKEN_LEN` are skipped to avoid false positives.
    """
    if not word_set:
        return False
    for token in _tokenize_name(name):
        if len(token) < _MIN_FUZZY_TOKEN_LEN:
            continue
        if token.lower() in word_set:
            return True
    return False


def _get_public_names(surface: APISurface) -> list[str]:
    """Extract public API names from an APISurface."""
    names: list[str] = []
    names.extend(f.name for f in surface.functions)
    names.extend(c.name for c in surface.classes)
    return names


def _tokenize_name(name: str) -> set[str]:
    """Split a camelCase / PascalCase / snake_case name into component tokens.

    The full name is always included in the returned set, plus every component word
    with length >= ``_MIN_FUZZY_TOKEN_LEN``. Tokens shorter than that are dropped to
    avoid false-positive matches on single letters (e.g. "T" from "TypeVar").

    Examples:
        "BM25Scorer" -> {"BM25Scorer", "bm25scorer", "BM25", "bm25", "Scorer", "scorer"}
        "get_user_id" -> {"get_user_id", "user"}  ("get" and "id" are < 4 chars)
    """
    tokens: set[str] = {name, name.lower()}

    # Snake-case split first, then camel-split each piece.
    for snake_part in name.split("_"):
        if not snake_part:
            continue
        for match in _CAMEL_SPLIT_RE.finditer(snake_part):
            piece = match.group(0)
            if len(piece) >= _MIN_FUZZY_TOKEN_LEN:
                tokens.add(piece)
                tokens.add(piece.lower())
    return tokens


def _name_covered_by_prose(name: str, prose: str) -> bool:
    """Return True if ``name`` or any long-enough token appears in ``prose``.

    Matching is case-insensitive. Tokens shorter than ``_MIN_FUZZY_TOKEN_LEN`` are
    ignored to keep single letters from triggering matches.
    """
    if not prose:
        return False
    prose_lower = prose.lower()
    for token in _tokenize_name(name):
        if len(token) < _MIN_FUZZY_TOKEN_LEN:
            continue
        if token.lower() in prose_lower:
            return True
    return False


def _name_covered_by_docstring(name: str, docstring_corpus_lower: str) -> bool:
    """Return True if ``name`` is mentioned in the symbol's docstring corpus.

    Matches the literal name (case-insensitive) or the name with underscores removed
    (so a snake_case mention like ``flashrank_reranker`` covers ``FlashRankReranker``).
    Unlike :func:`_name_covered_by_prose`, this does NOT fuzzy-match individual
    component tokens — a docstring that mentions "payments" must not be treated as
    covering the class ``PaymentProcessor``.
    """
    if not docstring_corpus_lower or not name:
        return False
    name_lower = name.lower()
    if name_lower in docstring_corpus_lower:
        return True
    # Underscore-insensitive: "flashrank_reranker" covers "FlashRankReranker".
    normalized_name = name_lower.replace("_", "")
    if len(normalized_name) >= _MIN_FUZZY_TOKEN_LEN:
        normalized_corpus = docstring_corpus_lower.replace("_", "")
        if normalized_name in normalized_corpus:
            return True
    return False


def _collect_docstrings_from_source(source: str) -> str:
    """Return concatenated module/class/function docstrings from pre-read source.

    Falls back to empty string on parse errors. The output is lowercased so callers
    can do case-insensitive substring checks.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    parts: list[str] = []
    module_doc = ast.get_docstring(tree)
    if module_doc:
        parts.append(module_doc)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                parts.append(doc)
    return "\n".join(parts).lower()


def _matches_any_pattern(qualified_name: str, patterns: list[str]) -> bool:
    """Return True if ``qualified_name`` matches any fnmatch-style glob pattern."""
    for pat in patterns:
        if fnmatch.fnmatchcase(qualified_name, pat):
            return True
        # Also match the bare symbol tail so patterns like "_*" work on qualified names.
        tail = qualified_name.rsplit(".", 1)[-1]
        if fnmatch.fnmatchcase(tail, pat):
            return True
    return False


def _qualify(rel_path: str, name: str) -> str:
    """Build a dotted fully-qualified symbol name from a relative file path.

    ``pkg/mod.py`` + ``Foo`` -> ``pkg.mod.Foo``. Strips common src-layout prefixes
    (``src/``, ``lib/``) so that ``ignore_patterns`` like ``pkg.mod.*`` work correctly
    on projects that follow a src-layout convention. Trailing ``/__init__.py`` is
    stripped so package symbols look natural.
    """
    path = rel_path.replace("\\", "/")
    if path.endswith("/__init__.py"):
        path = path[: -len("/__init__.py")]
    elif path.endswith(".py"):
        path = path[:-3]
    # Strip src-layout prefixes so logical package names are used in qualified names.
    for prefix in ("src/", "lib/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    module = path.replace("/", ".")
    return f"{module}.{name}" if module else name


class DriftDetector:
    """Detect documentation drift relative to code changes."""

    def check(
        self,
        project_root: Path,
        *,
        since: str | None = None,
        doc_dirs: list[str] | None = None,
        source_files: list[str] | None = None,
        docstring_coverage_counts: bool = True,
        ignore_patterns: list[str] | str | None = None,
    ) -> DriftReport:
        """Run drift detection.

        Args:
            project_root: Root of the project to scan.
            since: Unused for MVP (reserved for git ref/date filtering).
            doc_dirs: Optional list of directories containing docs.
            source_files: Optional list of relative path suffixes (e.g.
                ``["server.py", "tools/init.py"]``) to scope the scan to. Files
                are matched by ``endswith`` against their relative path so partial
                path tails work. When None (default), all Python files are scanned.
            docstring_coverage_counts: When True (default), a symbol's own module /
                class / function docstring can "cover" it even if external prose
                doesn't mention the name. Set to False for strict mode that only
                counts prose in documentation files.
            ignore_patterns: Fully-qualified symbol-name globs (e.g.
                ``"mypkg.cli.*"``) that are never flagged as drifted. Pass the
                sentinel string ``"defaults"`` to use :data:`_DEFAULT_IGNORE_PATTERNS`
                (``_*``, ``test_*``, ``tests.*``, ``*._*``). The defaults list is
                *not* applied automatically — callers must opt in — so existing
                behavior is preserved.

        Returns:
            A DriftReport with drift findings. ``drift_score`` is 0-100; the raw
            fraction is preserved in ``drift_fraction``.
        """
        if not project_root.is_dir():
            return DriftReport()

        py_files = _find_python_files(project_root)
        doc_files = _find_doc_files(project_root, doc_dirs)

        # Pre-filter by source_files to skip unneeded files before analysis.
        if source_files:
            normalised_sf = {sf.replace("\\", "/").lower() for sf in source_files}
            py_files = [
                f for f in py_files
                if any(
                    str(f.relative_to(project_root)).replace("\\", "/").lower().endswith(sf)
                    for sf in normalised_sf
                )
            ]

        if not py_files:
            return DriftReport()

        # Resolve ignore patterns.
        if ignore_patterns == "defaults":
            resolved_ignore: list[str] = list(_DEFAULT_IGNORE_PATTERNS)
        elif isinstance(ignore_patterns, list):
            resolved_ignore = list(ignore_patterns)
        else:
            resolved_ignore = []

        # Build token→mtime map: O(1) word lookups + per-file mtime precision.
        doc_token_mtime = _build_doc_token_mtime_map(doc_files)
        doc_word_set = frozenset(doc_token_mtime)

        # Global fallback mtime (used when no doc file mentions any token of a code file).
        doc_mtime: float = max(doc_token_mtime.values(), default=0.0)

        items: list[DriftItem] = []
        checked = 0

        from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

        analyzer = APISurfaceAnalyzer()

        for py_file in py_files:
            rel_path = str(py_file.relative_to(project_root)).replace("\\", "/")
            # Skip test files — test helpers/fixtures are not public API
            if "test" in rel_path.lower():
                continue

            # Single file read shared across empty-check, API analysis, and docstrings.
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            stripped = content.strip()
            if not stripped or stripped == '""""""':
                continue

            checked += 1

            try:
                code_mtime = py_file.stat().st_mtime
            except OSError:
                continue

            code_iso = _iso_from_mtime(code_mtime)

            # Analyze public API using pre-read source (no second file read).
            surface = analyzer.analyze_from_source(py_file, content, project_root=project_root)
            public_names = _get_public_names(surface)

            if not public_names:
                continue

            # Per-file: max mtime of doc files mentioning any token of any public name.
            # Falls back to global doc_mtime when no doc covers any token from this file.
            relevant_doc_mtime = _get_relevant_doc_mtime(public_names, doc_token_mtime)
            effective_doc_mtime = relevant_doc_mtime if relevant_doc_mtime > 0 else doc_mtime
            doc_iso = _iso_from_mtime(effective_doc_mtime) if effective_doc_mtime > 0 else ""

            # Docstring corpus from pre-read source (no third file read or AST re-parse).
            docstring_corpus = _collect_docstrings_from_source(content) if docstring_coverage_counts else ""

            # Check each public name against doc content + optional docstring + ignores
            undocumented: list[str] = []
            for name in public_names:
                qualified = _qualify(rel_path, name)
                if resolved_ignore and _matches_any_pattern(qualified, resolved_ignore):
                    continue
                if _name_covered_by_word_set(name, doc_word_set):
                    continue
                if docstring_coverage_counts and _name_covered_by_docstring(name, docstring_corpus):
                    continue
                undocumented.append(name)

            if undocumented:
                # Determine severity using per-file relevant doc mtime (reduces false-positive
                # errors when one unrelated doc is touched but relevant docs are stale).
                severity = "warning"
                if effective_doc_mtime > 0 and code_mtime > effective_doc_mtime:
                    severity = "error"

                drift_type = "added_undocumented"
                if effective_doc_mtime > 0 and code_mtime > effective_doc_mtime:
                    drift_type = "modified_undocumented"

                items.append(
                    DriftItem(
                        file_path=rel_path,
                        drift_type=drift_type,
                        severity=severity,
                        description=(
                            f"Public names not found in docs: {', '.join(undocumented[:5])}"
                            + (f" (+{len(undocumented) - 5} more)" if len(undocumented) > 5 else "")
                        ),
                        symbols=list(undocumented),
                        code_last_modified=code_iso,
                        doc_last_modified=doc_iso,
                    )
                )

        # Calculate drift fraction (0.0-1.0), then normalise to 0-100 for the public field.
        drift_fraction = len(items) / checked if checked > 0 else 0.0
        drift_fraction = min(drift_fraction, 1.0)
        drift_score = round(drift_fraction * 100.0, 1)

        return DriftReport(
            total_items=len(items),
            items=items,
            drift_score=drift_score,
            drift_fraction=round(drift_fraction, 3),
            checked_files=checked,
        )
