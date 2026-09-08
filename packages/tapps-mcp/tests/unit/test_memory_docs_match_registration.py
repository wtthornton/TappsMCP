"""The tapps_memory migration doc must not claim the tool was removed.

TAP-3895 / ADR-0016 restored `tapps_memory` as a supported slim facade on the
`nlt-memory` profile (commit 7486cc34, 2026-06-13). The migration doc drifted
and kept saying "REMOVED" / "no longer registered in any server preset" for
months after that. This test asserts the doc no longer carries those retired
claims, and derives the "tapps_memory is registered" fact from the actual
profile table rather than restating it.
"""

from __future__ import annotations

import re
from pathlib import Path

from tapps_mcp.cli_memory import memory_group
from tapps_mcp.server import TOOL_PROFILE_NLT_MEMORY
from tapps_mcp.server_memory_tools import _LIFECYCLE_ACTIONS, NLT_MEMORY_SLIM_ACTIONS

_DOC_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "migrations" / "tapps-memory-deprecation.md"
)

_RETIRED_PHRASES = (
    "no longer registered in any server preset",
    "Status:** REMOVED",
)

_MCP_ACTIONS_BLOCK_RE = re.compile(
    r"<!-- mcp-actions:start -->(.*?)<!-- mcp-actions:end -->", re.DOTALL
)
_BACKTICK_TOKEN_RE = re.compile(r"`([a-z_]+)`")

_CLI_COMMANDS_BLOCK_RE = re.compile(
    r"<!-- cli-commands:start -->(.*?)<!-- cli-commands:end -->", re.DOTALL
)
_BACKTICK_CLI_TOKEN_RE = re.compile(r"`([a-z][a-z-]*)`")

_REFUSAL_CODE = "action_not_on_nlt_memory"


def test_migration_doc_does_not_claim_tool_removed() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    for phrase in _RETIRED_PHRASES:
        assert phrase not in text, f"migration doc still claims a retired state: {phrase!r}"


def test_tapps_memory_is_registered_on_nlt_memory_profile() -> None:
    assert "tapps_memory" in TOOL_PROFILE_NLT_MEMORY


def test_doc_mcp_action_list_matches_producer_exactly() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    match = _MCP_ACTIONS_BLOCK_RE.search(text)
    assert match is not None, "doc is missing the <!-- mcp-actions:start/end --> block"
    doc_actions = frozenset(_BACKTICK_TOKEN_RE.findall(match.group(1)))
    expected = NLT_MEMORY_SLIM_ACTIONS | _LIFECYCLE_ACTIONS
    assert doc_actions == expected, (
        f"doc's MCP action list {sorted(doc_actions)} does not match the producer's "
        f"NLT_MEMORY_SLIM_ACTIONS | _LIFECYCLE_ACTIONS {sorted(expected)}"
    )


def test_doc_names_the_refusal_code_the_module_actually_returns() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    assert _REFUSAL_CODE in text, f"doc must name the literal refusal code {_REFUSAL_CODE!r}"


def test_doc_has_no_stale_q3_date_labels() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    assert "2026-Q3" not in text, "doc still carries a wrong 2026-Q3 date label"


def test_doc_cli_command_list_matches_producer_exactly() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    match = _CLI_COMMANDS_BLOCK_RE.search(text)
    assert match is not None, "doc is missing the <!-- cli-commands:start/end --> block"
    doc_commands = frozenset(_BACKTICK_CLI_TOKEN_RE.findall(match.group(1)))
    expected = frozenset(memory_group.commands.keys())
    assert doc_commands == expected, (
        f"doc's CLI-command list {sorted(doc_commands)} does not match the producer's "
        f"@memory_group.command(...) names {sorted(expected)}"
    )


def test_doc_h1_no_longer_claims_deprecation_migration_table() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    h1 = text.splitlines()[0]
    assert "Deprecation Migration Table" not in h1, f"H1 still stale: {h1!r}"
