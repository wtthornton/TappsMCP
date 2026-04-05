"""Regex-based fallback extractor for any text-based source file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from docs_mcp.extractors.models import (
    ClassInfo,
    ConstantInfo,
    FunctionInfo,
    ModuleInfo,
    ParameterInfo,
)


@dataclass(frozen=True)
class LanguagePatterns:
    """Regex patterns for extracting symbols from a specific language."""

    function: re.Pattern[str] | None = None
    class_def: re.Pattern[str] | None = None
    import_stmt: re.Pattern[str] | None = None
    constant: re.Pattern[str] | None = None
    doc_comment_prefix: str | None = None
    block_comment_start: str | None = None
    block_comment_end: str | None = None


# -- Python patterns ----------------------------------------------------------

_PY_FUNC = re.compile(
    r"^([^\S\n]*)(async\s+)?def\s+(\w+)\s*\(([^)]*)\)(\s*->\s*[^:]+)?:",
    re.MULTILINE,
)
_PY_CLASS = re.compile(
    r"^([^\S\n]*)class\s+(\w+)(\(([^)]*)\))?:",
    re.MULTILINE,
)
_PY_IMPORT = re.compile(
    r"^(?:from\s+\S+\s+)?import\s+.+",
    re.MULTILINE,
)
_PY_CONSTANT = re.compile(
    r"^([A-Z][A-Z_0-9]+)\s*[=:]",
    re.MULTILINE,
)
_PY_ALL = re.compile(
    r"^__all__\s*=\s*\[([^\]]*)\]",
    re.MULTILINE | re.DOTALL,
)
_PY_MAIN = re.compile(
    r'^if\s+__name__\s*==\s*["\']__main__["\']',
    re.MULTILINE,
)
_PY_TRIPLE_DQ = re.compile(r'"""(.*?)"""', re.DOTALL)
_PY_TRIPLE_SQ = re.compile(r"'''(.*?)'''", re.DOTALL)

# -- JS/TS patterns -----------------------------------------------------------

_JS_FUNC = re.compile(
    r"^\s*(export\s+)?(async\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_JS_ARROW = re.compile(
    r"^\s*(export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(async\s+)?\(",
    re.MULTILINE,
)
_JS_CLASS = re.compile(
    r"^\s*(export\s+)?class\s+(\w+)(\s+extends\s+(\w+))?",
    re.MULTILINE,
)
_JS_IMPORT = re.compile(
    r"^import\s+.+",
    re.MULTILINE,
)
_JS_JSDOC = re.compile(
    r"/\*\*(.*?)\*/",
    re.DOTALL,
)

# -- Go patterns ---------------------------------------------------------------

_GO_FUNC = re.compile(
    r"^func\s+(\w+)\s*\(",
    re.MULTILINE,
)
_GO_METHOD = re.compile(
    r"^func\s+\(\w+\s+\*?\w+\)\s+(\w+)\s*\(",
    re.MULTILINE,
)
_GO_TYPE = re.compile(
    r"^type\s+(\w+)\s+(struct|interface)",
    re.MULTILINE,
)
_GO_IMPORT = re.compile(
    r"^import\s+",
    re.MULTILINE,
)

# -- Rust patterns -------------------------------------------------------------

_RS_FUNC = re.compile(
    r"^\s*(pub\s+)?(async\s+)?fn\s+(\w+)",
    re.MULTILINE,
)
_RS_STRUCT = re.compile(
    r"^\s*(pub\s+)?struct\s+(\w+)",
    re.MULTILINE,
)
_RS_IMPL = re.compile(
    r"^\s*impl(?:\s+\w+)?\s+(\w+)",
    re.MULTILINE,
)
_RS_DOC = re.compile(
    r"^(\s*///.*\n)+",
    re.MULTILINE,
)

# Max file size to read (10 MB) to avoid OOM on huge files.
_MAX_FILE_SIZE = 10 * 1024 * 1024


@dataclass
class _ExtractionState:
    """Mutable state accumulated during extraction."""

    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    constants: list[ConstantInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    docstring: str | None = None
    has_main_block: bool = False
    all_exports: list[str] | None = None


class GenericExtractor:
    """Regex-based fallback extractor for any text-based source file.

    Always succeeds: catches all exceptions and returns an empty ``ModuleInfo``
    on total failure.  Designed as the last-resort extractor when AST parsing
    fails or the file is not Python.
    """

    LANGUAGE_MAP: ClassVar[dict[str, str]] = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".go": "go",
        ".rs": "rust",
    }

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def can_handle(self, file_path: Path) -> bool:
        """Accept any file — this is the universal fallback."""
        return True

    def extract(
        self,
        file_path: Path,
        *,
        project_root: Path | None = None,
    ) -> ModuleInfo:
        """Extract symbols via regex. Never raises."""
        rel_path = _relative_path(file_path, project_root)
        try:
            return self._do_extract(file_path, rel_path)
        except Exception:
            return ModuleInfo(path=rel_path)

    # ------------------------------------------------------------------
    # Internal extraction
    # ------------------------------------------------------------------

    def _do_extract(self, file_path: Path, rel_path: str) -> ModuleInfo:
        if not file_path.exists():
            return ModuleInfo(path=rel_path)

        # Guard against huge files.
        try:
            size = file_path.stat().st_size
        except OSError:
            return ModuleInfo(path=rel_path)
        if size > _MAX_FILE_SIZE:
            return ModuleInfo(path=rel_path)

        content = self._read_file(file_path)
        if content is None:
            return ModuleInfo(path=rel_path)

        lang = self.LANGUAGE_MAP.get(file_path.suffix.lower(), "unknown")
        state = _ExtractionState()

        if lang == "python":
            self._extract_python(content, state)
        elif lang in ("javascript", "typescript"):
            self._extract_js_ts(content, state)
        elif lang == "go":
            self._extract_go(content, state)
        elif lang == "rust":
            self._extract_rust(content, state)
        else:
            # Unknown language: try to grab a leading comment as docstring.
            state.docstring = _extract_leading_comment(content)

        return ModuleInfo(
            path=rel_path,
            docstring=state.docstring,
            imports=state.imports,
            functions=state.functions,
            classes=state.classes,
            constants=state.constants,
            has_main_block=state.has_main_block,
            all_exports=state.all_exports,
        )

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    @staticmethod
    def _read_file(file_path: Path) -> str | None:
        """Read a file, returning ``None`` for binary or unreadable files."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return None
        # Heuristic: if the replacement character appears a lot, treat as binary.
        if text.count("\ufffd") > len(text) * 0.1:
            return None
        return text

    # ------------------------------------------------------------------
    # Python extraction
    # ------------------------------------------------------------------

    def _extract_python(self, content: str, state: _ExtractionState) -> None:
        lines = content.split("\n")
        state.docstring = _extract_python_module_docstring(content)
        state.has_main_block = bool(_PY_MAIN.search(content))
        state.all_exports = _extract_python_all(content)
        state.imports = [m.group(0).strip() for m in _PY_IMPORT.finditer(content)]

        # Constants (module-level only — no leading whitespace).
        for m in _PY_CONSTANT.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            state.constants.append(ConstantInfo(name=m.group(1), line=line_no))

        # Classes.
        for m in _PY_CLASS.finditer(content):
            indent = m.group(1)
            if indent.strip() == "" and len(indent) == 0:
                # Top-level class.
                line_no = content[: m.start()].count("\n") + 1
                name = m.group(2)
                bases_raw = m.group(4) or ""
                bases = [b.strip() for b in bases_raw.split(",") if b.strip()]
                doc = _extract_docstring_after(lines, line_no - 1)
                state.classes.append(
                    ClassInfo(
                        name=name,
                        line=line_no,
                        bases=bases,
                        docstring=doc,
                    )
                )

        # Functions (top-level — no leading whitespace).
        for m in _PY_FUNC.finditer(content):
            indent = m.group(1)
            if indent.strip() == "" and len(indent) == 0:
                line_no = content[: m.start()].count("\n") + 1
                is_async = m.group(2) is not None
                name = m.group(3)
                params_raw = m.group(4) or ""
                ret = (m.group(5) or "").strip()
                if ret.startswith("->"):
                    ret = ret[2:].strip()
                else:
                    ret = None
                sig = f"({params_raw})"
                if ret:
                    sig += f" -> {ret}"
                parameters = _parse_python_params(params_raw)
                doc = _extract_docstring_after(lines, line_no - 1)
                state.functions.append(
                    FunctionInfo(
                        name=name,
                        line=line_no,
                        signature=sig,
                        parameters=parameters,
                        return_annotation=ret if ret else None,
                        is_async=is_async,
                        docstring=doc,
                    )
                )

    # ------------------------------------------------------------------
    # JavaScript / TypeScript extraction
    # ------------------------------------------------------------------

    def _extract_js_ts(self, content: str, state: _ExtractionState) -> None:
        lines = content.split("\n")
        state.imports = [m.group(0).strip() for m in _JS_IMPORT.finditer(content)]

        # Collect JSDoc blocks indexed by the line they end on.
        jsdoc_by_end_line: dict[int, str] = {}
        for m in _JS_JSDOC.finditer(content):
            end_line = content[: m.end()].count("\n")
            body = m.group(1)
            # Strip leading * from each line.
            cleaned = "\n".join(
                line.strip().lstrip("*").strip()
                for line in body.split("\n")
            ).strip()
            if cleaned:
                jsdoc_by_end_line[end_line] = cleaned

        # Regular functions.
        for m in _JS_FUNC.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            is_async = m.group(2) is not None
            name = m.group(3)
            doc = _jsdoc_before(jsdoc_by_end_line, line_no, lines)
            state.functions.append(
                FunctionInfo(
                    name=name,
                    line=line_no,
                    signature="()",
                    is_async=is_async,
                    docstring=doc,
                )
            )

        # Arrow functions assigned to const/let/var.
        for m in _JS_ARROW.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(2)
            is_async = m.group(3) is not None
            doc = _jsdoc_before(jsdoc_by_end_line, line_no, lines)
            state.functions.append(
                FunctionInfo(
                    name=name,
                    line=line_no,
                    signature="()",
                    is_async=is_async,
                    docstring=doc,
                )
            )

        # Classes.
        for m in _JS_CLASS.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(2)
            base = m.group(4)
            bases = [base] if base else []
            doc = _jsdoc_before(jsdoc_by_end_line, line_no, lines)
            state.classes.append(
                ClassInfo(
                    name=name,
                    line=line_no,
                    bases=bases,
                    docstring=doc,
                )
            )

    # ------------------------------------------------------------------
    # Go extraction
    # ------------------------------------------------------------------

    def _extract_go(self, content: str, state: _ExtractionState) -> None:
        lines = content.split("\n")
        state.imports = [m.group(0).strip() for m in _GO_IMPORT.finditer(content)]

        # Functions.
        for m in _GO_FUNC.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(1)
            doc = _go_comment_before(lines, line_no - 1)
            state.functions.append(
                FunctionInfo(name=name, line=line_no, signature="()", docstring=doc)
            )

        # Methods.
        for m in _GO_METHOD.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(1)
            doc = _go_comment_before(lines, line_no - 1)
            state.functions.append(
                FunctionInfo(name=name, line=line_no, signature="()", docstring=doc)
            )

        # Type declarations (struct/interface).
        for m in _GO_TYPE.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(1)
            doc = _go_comment_before(lines, line_no - 1)
            state.classes.append(
                ClassInfo(name=name, line=line_no, docstring=doc)
            )

    # ------------------------------------------------------------------
    # Rust extraction
    # ------------------------------------------------------------------

    def _extract_rust(self, content: str, state: _ExtractionState) -> None:
        lines = content.split("\n")

        # Functions.
        for m in _RS_FUNC.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(3)
            is_async = m.group(2) is not None
            doc = _rust_doc_before(lines, line_no - 1)
            state.functions.append(
                FunctionInfo(
                    name=name,
                    line=line_no,
                    signature="()",
                    is_async=is_async,
                    docstring=doc,
                )
            )

        # Structs.
        for m in _RS_STRUCT.finditer(content):
            line_no = content[: m.start()].count("\n") + 1
            name = m.group(2)
            doc = _rust_doc_before(lines, line_no - 1)
            state.classes.append(
                ClassInfo(name=name, line=line_no, docstring=doc)
            )


# =========================================================================
# Helper functions
# =========================================================================


def _relative_path(file_path: Path, project_root: Path | None) -> str:
    """Make *file_path* relative to *project_root* when possible."""
    if project_root is not None:
        try:
            return str(file_path.relative_to(project_root))
        except ValueError:
            pass
    return str(file_path)


def _extract_leading_comment(content: str) -> str | None:
    """Extract a leading ``#``-comment block as a pseudo-docstring."""
    doc_lines: list[str] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            doc_lines.append(stripped.lstrip("#").strip())
        elif stripped == "":
            if doc_lines:
                break
        else:
            break
    return "\n".join(doc_lines).strip() or None


def _extract_python_module_docstring(content: str) -> str | None:
    """Extract a module-level triple-quoted docstring."""
    stripped = content.lstrip()
    for pattern in (_PY_TRIPLE_DQ, _PY_TRIPLE_SQ):
        m = pattern.match(stripped)
        if m:
            return m.group(1).strip() or None
    return None


def _extract_python_all(content: str) -> list[str] | None:
    """Extract ``__all__`` list if present."""
    m = _PY_ALL.search(content)
    if not m:
        return None
    raw = m.group(1)
    names = re.findall(r"""['"](\w+)['"]""", raw)
    return names if names else None


def _extract_docstring_after(lines: list[str], def_line_idx: int) -> str | None:
    """Look for a triple-quoted docstring on the lines after a def/class."""
    idx = def_line_idx + 1
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped == "":
            idx += 1
            continue
        # Single-line docstring.
        for q in ('"""', "'''"):
            if stripped.startswith(q) and stripped.endswith(q) and len(stripped) > 6:
                return stripped[3:-3].strip() or None
        # Multi-line docstring.
        for q in ('"""', "'''"):
            if stripped.startswith(q):
                doc_parts = [stripped[3:]]
                idx += 1
                while idx < len(lines):
                    line = lines[idx]
                    if q in line:
                        before_close = line.split(q)[0]
                        doc_parts.append(before_close)
                        return "\n".join(doc_parts).strip() or None
                    doc_parts.append(line.strip())
                    idx += 1
                return "\n".join(doc_parts).strip() or None
        # Not a docstring line — stop looking.
        break
    return None


def _parse_python_params(raw: str) -> list[ParameterInfo]:
    """Parse a raw parameter string into ``ParameterInfo`` objects."""
    params: list[ParameterInfo] = []
    if not raw.strip():
        return params
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Skip *args, **kwargs markers for now.
        if part in ("*", "/"):
            continue
        name = part.split(":")[0].split("=")[0].strip().lstrip("*")
        if name:
            annotation: str | None = None
            default: str | None = None
            if ":" in part:
                rest_after_name = part.split(":", 1)[1]
                if "=" in rest_after_name:
                    annotation = rest_after_name.split("=")[0].strip() or None
                    default = rest_after_name.split("=", 1)[1].strip() or None
                else:
                    annotation = rest_after_name.strip() or None
            elif "=" in part:
                default = part.split("=", 1)[1].strip() or None
            params.append(
                ParameterInfo(name=name, annotation=annotation, default=default)
            )
    return params


def _jsdoc_before(
    jsdoc_by_end_line: dict[int, str],
    target_line: int,
    lines: list[str],
) -> str | None:
    """Find a JSDoc comment ending just before *target_line* (1-based)."""
    # Look on the line directly before the target (0-based index = target_line - 2).
    # JSDoc end-line is 0-based.
    for offset in range(1, 4):
        check = target_line - offset  # 1-based
        check_0 = check - 1  # 0-based
        if check_0 in jsdoc_by_end_line:
            return jsdoc_by_end_line[check_0]
        # Skip blank lines.
        if 0 <= check_0 < len(lines) and lines[check_0].strip() == "":
            continue
        break
    return None


def _go_comment_before(lines: list[str], def_line_idx: int) -> str | None:
    """Collect ``//`` comment lines immediately before a Go definition."""
    doc_lines: list[str] = []
    idx = def_line_idx - 1  # 0-based index of line before definition
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.startswith("//"):
            doc_lines.append(stripped.lstrip("/").strip())
            idx -= 1
        else:
            break
    if doc_lines:
        doc_lines.reverse()
        return "\n".join(doc_lines)
    return None


def _rust_doc_before(lines: list[str], def_line_idx: int) -> str | None:
    """Collect ``///`` doc-comment lines immediately before a Rust item."""
    doc_lines: list[str] = []
    idx = def_line_idx - 1
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.startswith("///"):
            doc_lines.append(stripped.lstrip("/").strip())
            idx -= 1
        else:
            break
    if doc_lines:
        doc_lines.reverse()
        return "\n".join(doc_lines)
    return None
