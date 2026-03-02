"""Docstring parser supporting Google, NumPy, and Sphinx styles.

Parses Python docstrings into structured data models without external
dependencies. Handles style auto-detection and graceful fallback for
malformed input.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DocstringParam(BaseModel):
    """A single parameter documented in a docstring."""

    name: str
    type: str | None = None
    description: str = ""


class DocstringReturns(BaseModel):
    """Return value documentation."""

    type: str | None = None
    description: str = ""


class DocstringRaises(BaseModel):
    """A single exception documented in a docstring."""

    exception: str
    description: str = ""


class DocstringExample(BaseModel):
    """A code example extracted from a docstring."""

    code: str
    description: str = ""


class ParsedDocstring(BaseModel):
    """Fully parsed docstring with all extracted sections."""

    summary: str = ""
    description: str = ""
    params: list[DocstringParam] = []
    returns: DocstringReturns | None = None
    raises: list[DocstringRaises] = []
    examples: list[DocstringExample] = []
    notes: str = ""
    style: str = "unknown"
    raw: str = ""


# ---------------------------------------------------------------------------
# Style detection
# ---------------------------------------------------------------------------

_GOOGLE_SECTIONS = re.compile(
    r"^\s*(Args|Arguments|Returns|Return|Raises|Yields|Examples?|Notes?|Attributes)\s*:",
    re.MULTILINE,
)

_NUMPY_HEADER = re.compile(
    r"^\s*(Parameters|Returns|Raises|Yields|Examples?|Notes?|Attributes)"
    r"\s*\n\s*-{3,}",
    re.MULTILINE,
)

_SPHINX_DIRECTIVES = re.compile(
    r"^\s*:(param|type|returns|rtype|raises)[\s:]",
    re.MULTILINE,
)


def _detect_style(docstring: str) -> str:
    """Detect the docstring style using simple heuristics."""
    if _NUMPY_HEADER.search(docstring):
        return "numpy"
    if _GOOGLE_SECTIONS.search(docstring):
        return "google"
    if _SPHINX_DIRECTIVES.search(docstring):
        return "sphinx"
    return "unknown"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _extract_summary_and_description(
    docstring: str,
    section_start: int | None,
) -> tuple[str, str]:
    """Extract the summary (first non-empty line) and body description.

    ``section_start`` is the character index where the first recognised
    section begins.  Everything between the summary paragraph and that
    index is considered the extended description.
    """
    text = docstring[:section_start] if section_start is not None else docstring
    lines = text.split("\n")

    summary = ""
    body_lines: list[str] = []
    found_summary = False
    past_summary_gap = False

    for line in lines:
        stripped = line.strip()
        if not found_summary:
            if stripped:
                summary = stripped
                found_summary = True
            continue

        if not past_summary_gap:
            if not stripped:
                past_summary_gap = True
            continue

        body_lines.append(stripped)

    # Remove trailing blank lines from description
    while body_lines and not body_lines[-1]:
        body_lines.pop()

    description = "\n".join(body_lines)
    return summary, description


def _find_first_section_google(docstring: str) -> int | None:
    """Return the start index of the first Google-style section header."""
    m = _GOOGLE_SECTIONS.search(docstring)
    return m.start() if m else None


def _find_first_section_numpy(docstring: str) -> int | None:
    """Return the start index of the first NumPy-style section header."""
    m = _NUMPY_HEADER.search(docstring)
    return m.start() if m else None


def _find_first_section_sphinx(docstring: str) -> int | None:
    """Return the start index of the first Sphinx directive."""
    m = _SPHINX_DIRECTIVES.search(docstring)
    return m.start() if m else None


# ---------------------------------------------------------------------------
# Google-style parser
# ---------------------------------------------------------------------------

_GOOGLE_SECTION_RE = re.compile(
    r"^\s*(Args|Arguments|Returns|Return|Raises|Yields|Examples?|Notes?|Attributes)\s*:\s*$",
    re.MULTILINE,
)


def _split_google_sections(docstring: str) -> dict[str, str]:
    """Split a Google-style docstring into named section bodies."""
    matches = list(_GOOGLE_SECTION_RE.finditer(docstring))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        # Normalise aliases
        if name == "arguments":
            name = "args"
        if name == "return":
            name = "returns"
        if name in ("example",):
            name = "examples"
        if name == "note":
            name = "notes"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(docstring)
        sections[name] = docstring[start:end]
    return sections


def _parse_google_params(text: str) -> list[DocstringParam]:
    """Parse Google-style ``Args:`` entries."""
    params: list[DocstringParam] = []
    # Match lines like "  name (type): desc" or "  name: desc"
    entry_re = re.compile(
        r"^[ \t]+(\w+)"             # indented param name
        r"(?:\s*\(([^)]*)\))?"      # optional (type)
        r"\s*:\s*(.*)",             # : description
    )
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = entry_re.match(lines[i])
        if m:
            name = m.group(1)
            ptype = m.group(2).strip() if m.group(2) else None
            desc_parts = [m.group(3).strip()]
            # Collect continuation lines (indented further)
            i += 1
            while i < len(lines):
                line = lines[i]
                if not line.strip():
                    i += 1
                    continue
                # Continuation: indented and not a new param
                if entry_re.match(line):
                    break
                if line and line[0] in (" ", "\t"):
                    desc_parts.append(line.strip())
                    i += 1
                else:
                    break
            params.append(
                DocstringParam(
                    name=name,
                    type=ptype,
                    description=" ".join(p for p in desc_parts if p),
                )
            )
        else:
            i += 1
    return params


def _parse_google_returns(text: str) -> DocstringReturns | None:
    """Parse Google-style ``Returns:`` section."""
    stripped = text.strip()
    if not stripped:
        return None
    # Try "type: description"
    m = re.match(r"^(\w[\w\[\], |]*?):\s+(.+)", stripped, re.DOTALL)
    if m:
        return DocstringReturns(type=m.group(1).strip(), description=m.group(2).strip())
    return DocstringReturns(description=stripped)


def _parse_google_raises(text: str) -> list[DocstringRaises]:
    """Parse Google-style ``Raises:`` section."""
    raises: list[DocstringRaises] = []
    entry_re = re.compile(r"^[ \t]+(\w+)\s*:\s*(.*)")
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = entry_re.match(lines[i])
        if m:
            exc = m.group(1)
            desc_parts = [m.group(2).strip()]
            i += 1
            while i < len(lines):
                line = lines[i]
                if not line.strip():
                    i += 1
                    continue
                if entry_re.match(line):
                    break
                if line and line[0] in (" ", "\t"):
                    desc_parts.append(line.strip())
                    i += 1
                else:
                    break
            raises.append(
                DocstringRaises(
                    exception=exc,
                    description=" ".join(p for p in desc_parts if p),
                )
            )
        else:
            i += 1
    return raises


def _parse_google_examples(text: str) -> list[DocstringExample]:
    """Parse Google-style ``Examples:`` section."""
    examples: list[DocstringExample] = []
    code_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(">>>") or (code_lines and stripped):
            code_lines.append(stripped)
        elif code_lines and not stripped:
            # End of a code block
            examples.append(DocstringExample(code="\n".join(code_lines)))
            code_lines = []
    if code_lines:
        examples.append(DocstringExample(code="\n".join(code_lines)))
    return examples


def _parse_google(docstring: str) -> ParsedDocstring:
    """Parse a Google-style docstring."""
    section_start = _find_first_section_google(docstring)
    summary, description = _extract_summary_and_description(docstring, section_start)
    sections = _split_google_sections(docstring)

    params: list[DocstringParam] = []
    returns: DocstringReturns | None = None
    raises: list[DocstringRaises] = []
    examples: list[DocstringExample] = []
    notes = ""

    if "args" in sections:
        params = _parse_google_params(sections["args"])
    if "attributes" in sections:
        params.extend(_parse_google_params(sections["attributes"]))
    if "returns" in sections:
        returns = _parse_google_returns(sections["returns"])
    if "raises" in sections:
        raises = _parse_google_raises(sections["raises"])
    if "examples" in sections:
        examples = _parse_google_examples(sections["examples"])
    if "notes" in sections:
        notes = sections["notes"].strip()

    return ParsedDocstring(
        summary=summary,
        description=description,
        params=params,
        returns=returns,
        raises=raises,
        examples=examples,
        notes=notes,
        style="google",
        raw=docstring,
    )


# ---------------------------------------------------------------------------
# NumPy-style parser
# ---------------------------------------------------------------------------

_NUMPY_SECTION_RE = re.compile(
    r"^\s*(Parameters|Returns|Raises|Yields|Examples?|Notes?|Attributes)"
    r"\s*\n\s*-{3,}\s*$",
    re.MULTILINE,
)


def _split_numpy_sections(docstring: str) -> dict[str, str]:
    """Split a NumPy-style docstring into named section bodies."""
    matches = list(_NUMPY_SECTION_RE.finditer(docstring))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        if name == "example":
            name = "examples"
        if name == "note":
            name = "notes"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(docstring)
        sections[name] = docstring[start:end]
    return sections


def _parse_numpy_params(text: str) -> list[DocstringParam]:
    """Parse NumPy-style parameter entries.

    Each parameter is documented as::

        name : type
            Description that may span
            multiple lines.
    """
    params: list[DocstringParam] = []
    # Match "name : type" or just "name"
    header_re = re.compile(r"^[ \t]+(\w+)\s*(?::\s*(.+))?$")
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        m = header_re.match(lines[i])
        if m:
            name = m.group(1)
            ptype = m.group(2).strip() if m.group(2) else None
            desc_parts: list[str] = []
            i += 1
            while i < len(lines):
                line = lines[i]
                if not line.strip():
                    # Blank line might separate from next param
                    # Peek ahead: if next non-blank is a new header, stop
                    i += 1
                    continue
                if header_re.match(line) and not line.startswith("        "):
                    break
                desc_parts.append(line.strip())
                i += 1
            params.append(
                DocstringParam(
                    name=name,
                    type=ptype,
                    description=" ".join(desc_parts),
                )
            )
        else:
            i += 1
    return params


def _parse_numpy_returns(text: str) -> DocstringReturns | None:
    """Parse NumPy-style ``Returns`` section."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return None
    # First non-blank line might be "type" or "name : type"
    first = lines[0].strip()
    m = re.match(r"^(\w[\w\[\], |]*)$", first)
    if m:
        rtype = m.group(1)
        desc = " ".join(ln.strip() for ln in lines[1:])
        return DocstringReturns(type=rtype, description=desc)
    m2 = re.match(r"^(\w+)\s*:\s*(.+)$", first)
    if m2:
        rtype = m2.group(2).strip()
        desc = " ".join(ln.strip() for ln in lines[1:])
        return DocstringReturns(type=rtype, description=desc)
    desc = " ".join(ln.strip() for ln in lines)
    return DocstringReturns(description=desc)


def _parse_numpy_raises(text: str) -> list[DocstringRaises]:
    """Parse NumPy-style ``Raises`` section."""
    raises: list[DocstringRaises] = []
    header_re = re.compile(r"^[ \t]+(\w+)\s*$")
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        m = header_re.match(lines[i])
        if m:
            exc = m.group(1)
            desc_parts: list[str] = []
            i += 1
            while i < len(lines):
                line = lines[i]
                if not line.strip():
                    i += 1
                    continue
                if header_re.match(line):
                    break
                desc_parts.append(line.strip())
                i += 1
            raises.append(
                DocstringRaises(
                    exception=exc,
                    description=" ".join(desc_parts),
                )
            )
        else:
            i += 1
    return raises


def _parse_numpy(docstring: str) -> ParsedDocstring:
    """Parse a NumPy-style docstring."""
    section_start = _find_first_section_numpy(docstring)
    summary, description = _extract_summary_and_description(docstring, section_start)
    sections = _split_numpy_sections(docstring)

    params: list[DocstringParam] = []
    returns: DocstringReturns | None = None
    raises: list[DocstringRaises] = []
    examples: list[DocstringExample] = []
    notes = ""

    if "parameters" in sections:
        params = _parse_numpy_params(sections["parameters"])
    if "attributes" in sections:
        params.extend(_parse_numpy_params(sections["attributes"]))
    if "returns" in sections:
        returns = _parse_numpy_returns(sections["returns"])
    if "raises" in sections:
        raises = _parse_numpy_raises(sections["raises"])
    if "examples" in sections:
        examples = _parse_google_examples(sections["examples"])  # same >>> format
    if "notes" in sections:
        notes = sections["notes"].strip()

    return ParsedDocstring(
        summary=summary,
        description=description,
        params=params,
        returns=returns,
        raises=raises,
        examples=examples,
        notes=notes,
        style="numpy",
        raw=docstring,
    )


# ---------------------------------------------------------------------------
# Sphinx-style parser
# ---------------------------------------------------------------------------


def _parse_sphinx(docstring: str) -> ParsedDocstring:
    """Parse a Sphinx (reST) style docstring."""
    section_start = _find_first_section_sphinx(docstring)
    summary, description = _extract_summary_and_description(docstring, section_start)

    # Collect all directive lines with their continuations
    directive_re = re.compile(
        r"^\s*:(\w+)(?:\s+(\w+))?\s*:\s*(.*)",
    )
    lines = docstring.split("\n")

    params: dict[str, DocstringParam] = {}
    returns: DocstringReturns | None = None
    raises: list[DocstringRaises] = []

    i = 0
    while i < len(lines):
        m = directive_re.match(lines[i])
        if not m:
            i += 1
            continue

        kind = m.group(1)
        arg = m.group(2)
        text = m.group(3).strip()

        # Collect continuation lines
        desc_parts = [text] if text else []
        i += 1
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if directive_re.match(line):
                break
            if line and line[0] in (" ", "\t"):
                desc_parts.append(line.strip())
                i += 1
            else:
                break

        full_desc = " ".join(p for p in desc_parts if p)

        if kind == "param" and arg:
            if arg not in params:
                params[arg] = DocstringParam(name=arg)
            params[arg].description = full_desc
        elif kind == "type" and arg:
            if arg not in params:
                params[arg] = DocstringParam(name=arg)
            params[arg].type = full_desc
        elif kind == "returns":
            if returns is None:
                returns = DocstringReturns()
            returns.description = full_desc
        elif kind == "rtype":
            if returns is None:
                returns = DocstringReturns()
            returns.type = full_desc
        elif kind == "raises" and arg:
            raises.append(DocstringRaises(exception=arg, description=full_desc))

    return ParsedDocstring(
        summary=summary,
        description=description,
        params=list(params.values()),
        returns=returns,
        raises=raises,
        style="sphinx",
        raw=docstring,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_docstring(docstring: str, style: str = "auto") -> ParsedDocstring:
    """Parse a docstring into structured components.

    Args:
        docstring: The raw docstring text.
        style: Parsing style - ``"auto"`` (default), ``"google"``,
            ``"numpy"``, ``"sphinx"``, or ``"unknown"``.

    Returns:
        A ``ParsedDocstring`` containing the extracted sections.
    """
    if not docstring or not docstring.strip():
        return ParsedDocstring(raw=docstring or "")

    # Dedent: remove common leading whitespace
    docstring = _dedent(docstring)

    if style == "auto":
        style = _detect_style(docstring)

    if style == "google":
        return _parse_google(docstring)
    if style == "numpy":
        return _parse_numpy(docstring)
    if style == "sphinx":
        return _parse_sphinx(docstring)

    # Unknown style: extract summary and description only
    summary, description = _extract_summary_and_description(docstring, None)
    return ParsedDocstring(
        summary=summary,
        description=description,
        style="unknown",
        raw=docstring,
    )


def _dedent(text: str) -> str:
    """Remove common leading whitespace from all lines."""
    lines = text.split("\n")
    # Find minimum indentation (ignoring empty lines)
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent
    if min_indent and min_indent > 0:
        lines = [line[min_indent:] if len(line) >= min_indent else line for line in lines]
    return "\n".join(lines)
