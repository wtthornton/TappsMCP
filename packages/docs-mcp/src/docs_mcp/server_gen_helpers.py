"""Shared helpers for the DocsMCP generation tools.

Wire-format tag stripping (TAP-1552), the CSV / acceptance-criteria splitters
(TAP-5357), and the settings / call-recording seam. Split out of
``server_gen_tools.py`` under TAP-5608 so the generation handlers and their
facade stay under the quality gate's maintainability budget.

``get_settings`` and ``record_call`` re-resolve their targets from
:mod:`docs_mcp.server_gen_tools` on every call rather than binding at import
time. That module stays the single seam for the whole generation surface, so
``unittest.mock.patch("docs_mcp.server_gen_tools._get_settings", ...)`` keeps
working for the handlers that moved into the family siblings — the same
approach ``server_linear_tools`` took under TAP-5606.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docs_mcp.config.settings import DocsMCPSettings


def get_settings() -> DocsMCPSettings:
    """Resolve DocsMCP settings through the ``server_gen_tools`` seam."""
    from docs_mcp import server_gen_tools

    return server_gen_tools._get_settings()


def record_call(tool_name: str) -> None:
    """Record a tool call through the ``server_gen_tools`` seam."""
    from docs_mcp import server_gen_tools

    server_gen_tools._record_call(tool_name)


# TAP-1552: MCP function-call wire-format wrappers occasionally leak into
# parameter values when a caller (or upstream wrapper) mis-encodes multi-line
# content. The leaks observed in the wild are (a) `<parameter name="X">` /
# `</parameter>` from the Anthropic tool-use envelope and (b) bare tags named
# after the parameter itself, e.g. `</purpose_and_intent>`. We strip both
# shapes — but only for the closed list of names we know docs_generate_epic /
# docs_generate_story accept — so legitimate `<foo>` content in a user value
# (HTML/XML examples, code fences) survives intact.
_WIRE_TAG_NAMES = (
    "parameter",
    "purpose_and_intent",
    "goal",
    "motivation",
    "role",
    "want",
    "so_that",
    "description",
    "acceptance_criteria",
    "technical_notes",
    "risks",
    "non_goals",
    "success_metrics",
    "stakeholders",
    "references",
    "stories",
    "tasks",
    "dependencies",
    "blocks",
    "files",
    "test_cases",
    "estimated_loe",
    "status",
    "priority",
    "points",
    "size",
    "title",
    "number",
    "story_number",
    "epic_number",
    "criteria_format",
    "epic_path",
)


_STRIP_WIRE_TAGS = re.compile(
    r"</?(?:" + "|".join(_WIRE_TAG_NAMES) + r")(?:\s+[^>]*)?>",
    re.IGNORECASE,
)


def _strip_wire_tags(value: str) -> str:
    """Strip MCP function-call wire-format wrappers from a parameter value.

    See TAP-1552 — bare ``</purpose_and_intent>`` and ``<parameter name="X">``
    tokens occasionally leak into multi-line string parameters and end up
    rendered into the markdown body. The list of stripped names is closed
    (see ``_WIRE_TAG_NAMES``) so unrelated XML/HTML in user content is left
    alone.
    """
    return _STRIP_WIRE_TAGS.sub("", value) if value else value


def _split_csv(value: str) -> list[str]:
    """Split a comma-separated string into a trimmed list, dropping blanks.

    Each item is passed through :func:`_strip_wire_tags` so leaked wire-format
    wrappers do not reach the generator's template (TAP-1552).
    """
    if not value:
        return []
    return [_strip_wire_tags(item.strip()) for item in value.split(",") if item.strip()]


# Leading checkbox / bullet markers agents paste when supplying criteria.
_CRITERIA_PREFIX_RE = re.compile(
    r"^\s*(?:[-*+]|\d+\.)\s*(?:\[[ xX]\]\s*)?",
)


def _split_criteria_list(value: str) -> list[str]:
    """Split acceptance criteria on newlines — never on commas (TAP-5357).

    Commas are ordinary English inside a criterion (e.g. ``either X, Y, or Z``).
    Multi-criterion inputs must be newline-separated. Optional leading
    ``- [ ]`` / bullet prefixes are stripped so pasted checkbox lists round-trip.
    """
    if not value:
        return []
    cleaned = _strip_wire_tags(value)
    raw_items = re.split(r"[\r\n]+", cleaned) if re.search(r"[\r\n]", cleaned) else [cleaned]
    items: list[str] = []
    for item in raw_items:
        text = _CRITERIA_PREFIX_RE.sub("", item).strip()
        if text:
            items.append(text)
    return items
