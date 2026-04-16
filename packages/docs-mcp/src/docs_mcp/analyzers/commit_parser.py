"""Conventional commit parser and heuristic classifier for DocsMCP.

Parses commit messages that follow the Conventional Commits specification
(``type(scope): description``). For non-conventional messages, falls back
to keyword-based heuristic classification.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ParsedCommit(BaseModel):
    """Result of parsing/classifying a single commit message."""

    type: str = ""
    scope: str = ""
    description: str = ""
    body: str = ""
    breaking: bool = False
    raw: str = ""
    is_conventional: bool = False


# ---------------------------------------------------------------------------
# Conventional commit regex
# ---------------------------------------------------------------------------

# Matches: type(scope)!: description
# Groups:  1=type  2=scope (without parens, optional)  3=! (optional)  4=description
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)"  # type (e.g. feat, fix)
    r"(?:\((?P<scope>[^)]*)\))?"  # optional (scope)
    r"(?P<bang>!)?"  # optional breaking-change indicator
    r":\s*(?P<desc>.+)",  # colon + description
)


def parse_conventional_commit(message: str) -> ParsedCommit:
    """Parse a message as a conventional commit.

    If the message does not match the conventional format, the returned
    ``ParsedCommit`` will have ``is_conventional=False`` and all
    type/scope/description fields empty except ``raw``.
    """
    if not message:
        return ParsedCommit(raw=message)

    # Split header from body (separated by blank line)
    parts = message.split("\n\n", 1)
    header = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""

    m = _CONVENTIONAL_RE.match(header)
    if not m:
        return ParsedCommit(raw=message)

    commit_type = m.group("type").lower()
    scope = m.group("scope") or ""
    bang = m.group("bang") is not None
    description = m.group("desc").strip()

    # Check for BREAKING CHANGE in body
    breaking = bang or _has_breaking_change_footer(body)

    return ParsedCommit(
        type=commit_type,
        scope=scope,
        description=description,
        body=body,
        breaking=breaking,
        raw=message,
        is_conventional=True,
    )


def _has_breaking_change_footer(body: str) -> bool:
    """Return True if the body contains a ``BREAKING CHANGE:`` footer."""
    if not body:
        return False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("BREAKING CHANGE:") or stripped.startswith("BREAKING-CHANGE:"):
            return True
    return False


# ---------------------------------------------------------------------------
# Keyword-based classifier (non-conventional fallback)
# ---------------------------------------------------------------------------

# Order matters — first match wins.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("fix", ["fix", "bug", "patch", "hotfix", "resolve"]),
    ("feat", ["add", "feature", "implement", "introduce"]),
    ("docs", ["doc", "readme", "changelog"]),
    ("refactor", ["refactor", "clean", "restructure"]),
    ("test", ["test"]),
]


def classify_commit(message: str) -> ParsedCommit:
    """Classify a commit message, preferring conventional parsing.

    If the message follows the conventional format it is parsed as such.
    Otherwise, keyword heuristics assign a best-guess ``type`` with
    ``is_conventional=False``.
    """
    parsed = parse_conventional_commit(message)
    if parsed.is_conventional:
        return parsed

    if not message:
        return ParsedCommit(raw=message)

    # Split header/body for non-conventional as well
    parts = message.split("\n\n", 1)
    header = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""

    lower = header.lower()

    commit_type = "chore"  # default fallback
    for ctype, keywords in _KEYWORD_RULES:
        for kw in keywords:
            # Use word-boundary-ish check: keyword at start, preceded by
            # space/punctuation, or as a standalone word.
            if re.search(rf"\b{re.escape(kw)}", lower):
                commit_type = ctype
                break
        else:
            continue
        break

    return ParsedCommit(
        type=commit_type,
        scope="",
        description=header,
        body=body,
        breaking=False,
        raw=message,
        is_conventional=False,
    )
