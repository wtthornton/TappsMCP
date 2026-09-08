"""The tapps_memory migration doc must not claim the tool was removed.

TAP-3895 / ADR-0016 restored `tapps_memory` as a supported slim facade on the
`nlt-memory` profile (commit 7486cc34, 2026-06-13). The migration doc drifted
and kept saying "REMOVED" / "no longer registered in any server preset" for
months after that. This test asserts the doc no longer carries those retired
claims, and derives the "tapps_memory is registered" fact from the actual
profile table rather than restating it.

Four review rounds in a row found the same species of defect: a correct derived
block sitting beside a hand-written prose sentence that conflated the two
surfaces — naming an MCP-only action as if the CLI could reach it, or pointing
the reader at `tapps-mcp memory <word>` for a `<word>` the click group does not
register. So the last three tests here guard the *class*, not the instance:
every CLI invocation in the doc must name a registered command, every
`action=` in the doc must name a dispatchable action, and no paragraph that
invokes the CLI may also lay claim to the MCP action surface. Each guard has a
control test that feeds it a known-bad string, so a guard that silently stops
matching fails instead of passing vacuously.
"""

from __future__ import annotations

import re
from pathlib import Path

from tapps_mcp.cli_memory import memory_group
from tapps_mcp.server import TOOL_PROFILE_NLT_MEMORY
from tapps_mcp.server_memory_tools import (
    _LIFECYCLE_ACTIONS,
    _VALID_ACTIONS,
    NLT_MEMORY_SLIM_ACTIONS,
)

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

_UNREACHABLE_BLOCK_RE = re.compile(
    r"<!-- unreachable-actions:start -->(.*?)<!-- unreachable-actions:end -->", re.DOTALL
)

# Every bare number the doc states about these sets lives inside one of these
# markers, so no count can drift away from the producer unnoticed.
_COUNT_MARKER_RE = re.compile(r"<!-- count:([a-z-]+) -->(\d+)<!-- /count -->")

# `tapps-mcp memory <word>` — the placeholder form `tapps-mcp memory <command>`
# deliberately does not match, since `<` is not a command-name character.
_CLI_INVOCATION_RE = re.compile(r"tapps-mcp memory ([a-z][a-z0-9-]*)")
_ACTION_KWARG_RE = re.compile(r"""action=["']?([a-z][a-z0-9_]*)["']?""")
# "MCP action" / "MCP actions" in prose. The literal marker names
# (`mcp-actions:start`, `<!-- count:mcp-actions -->`) are hyphenated and so do
# not match.
_MCP_ACTION_PHRASE_RE = re.compile(r"mcp\s+actions?\b", re.IGNORECASE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n")

_REFUSAL_CODE = "action_not_on_nlt_memory"


def _mcp_actions() -> frozenset[str]:
    """Actions `tapps_memory` will dispatch over MCP on the nlt-memory profile."""
    return NLT_MEMORY_SLIM_ACTIONS | _LIFECYCLE_ACTIONS


def _cli_commands() -> frozenset[str]:
    """Command names registered on the `tapps-mcp memory` click group."""
    return frozenset(memory_group.commands.keys())


def _name_matched_cli_commands() -> frozenset[str]:
    """CLI commands that share a name with a catalog action but are not MCP-callable."""
    return (_cli_commands() & frozenset(_VALID_ACTIONS)) - _mcp_actions()


def _unreachable_actions() -> frozenset[str]:
    """`_VALID_ACTIONS` minus the MCP surface minus the name-matched CLI commands."""
    valid = frozenset(_VALID_ACTIONS)
    return valid - _mcp_actions() - (_cli_commands() & valid)


def _cli_commands_named_in(text: str) -> frozenset[str]:
    return frozenset(_CLI_INVOCATION_RE.findall(text))


def _actions_named_in(text: str) -> frozenset[str]:
    return frozenset(_ACTION_KWARG_RE.findall(text))


def _cli_paragraphs_claiming_mcp_surface(text: str) -> list[str]:
    """Paragraphs that show a CLI invocation *and* lay claim to the MCP surface.

    Either by the generic phrase ("for the 7 reachable MCP actions ... use
    `tapps-mcp memory ...`") or by naming an action the CLI cannot reach.
    """
    mcp_only = _mcp_actions() - _cli_commands()
    offenders: list[str] = []
    for para in _PARAGRAPH_SPLIT_RE.split(text):
        if not _CLI_INVOCATION_RE.search(para):
            continue
        named = frozenset(_BACKTICK_TOKEN_RE.findall(para))
        if _MCP_ACTION_PHRASE_RE.search(para) or (named & mcp_only):
            offenders.append(para)
    return offenders


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


def test_doc_unreachable_action_list_matches_producer_formula() -> None:
    """The 34-action unreachable list is derived, not hand-restated (CLAUDE.md rule 6)."""
    text = _DOC_PATH.read_text(encoding="utf-8")
    match = _UNREACHABLE_BLOCK_RE.search(text)
    assert match is not None, "doc is missing the <!-- unreachable-actions:start/end --> block"
    doc_actions = frozenset(_BACKTICK_TOKEN_RE.findall(match.group(1)))
    expected = _unreachable_actions()
    assert doc_actions == expected, (
        f"doc's unreachable list is stale: only in doc {sorted(doc_actions - expected)}, "
        f"only in producer {sorted(expected - doc_actions)}"
    )


def test_doc_count_markers_match_the_producer() -> None:
    """No bare number about these sets may sit in prose unguarded."""
    text = _DOC_PATH.read_text(encoding="utf-8")
    expected = {
        "valid-actions": len(_VALID_ACTIONS),
        "mcp-actions": len(_mcp_actions()),
        "cli-commands": len(_cli_commands()),
        "name-matched": len(_name_matched_cli_commands()),
        "unreachable": len(_unreachable_actions()),
    }
    found = _COUNT_MARKER_RE.findall(text)
    assert found, "doc has no <!-- count:NAME -->N<!-- /count --> markers"
    seen: set[str] = set()
    for name, value in found:
        assert name in expected, f"doc states an unknown count marker {name!r}"
        assert int(value) == expected[name], (
            f"doc says {name} is {value}, producer says {expected[name]}"
        )
        seen.add(name)
    assert seen == set(expected), f"doc is missing count markers for {sorted(set(expected) - seen)}"


def test_every_cli_invocation_in_doc_names_a_registered_command() -> None:
    """Class guard: prose must not send the reader to a `tapps-mcp memory <word>` that is not real."""
    text = _DOC_PATH.read_text(encoding="utf-8")
    unregistered = _cli_commands_named_in(text) - _cli_commands()
    assert not unregistered, (
        f"doc invokes `tapps-mcp memory {sorted(unregistered)}` but cli_memory.py registers "
        f"only {sorted(_cli_commands())}"
    )


def test_cli_invocation_guard_rejects_an_unregistered_command() -> None:
    """Control for the guard above: it must fire on a known-bad string."""
    bogus = "run `uv run tapps-mcp memory health` and `tapps-mcp memory related` to check"
    assert _cli_commands_named_in(bogus) - _cli_commands() == {"health", "related"}
    assert not _cli_commands_named_in("run `tapps-mcp memory search --query x`") - _cli_commands()


def test_every_action_mention_in_doc_is_dispatchable_over_mcp() -> None:
    """Class guard: a backticked `action=<word>` must name something MCP will dispatch."""
    text = _DOC_PATH.read_text(encoding="utf-8")
    undispatchable = _actions_named_in(text) - _mcp_actions()
    assert not undispatchable, (
        f"doc writes action={sorted(undispatchable)} but nlt-memory dispatches only "
        f"{sorted(_mcp_actions())}"
    )


def test_action_mention_guard_rejects_an_undispatchable_action() -> None:
    """Control for the guard above: it must fire on a known-bad string."""
    assert _actions_named_in('call `tapps_memory(action="gc")`') - _mcp_actions() == {"gc"}
    assert not _actions_named_in('`action="health"`') - _mcp_actions()


def test_no_cli_paragraph_claims_the_mcp_action_surface() -> None:
    """Class guard: the r1/r2/r3 defect — one paragraph offering the CLI as an MCP route."""
    text = _DOC_PATH.read_text(encoding="utf-8")
    offenders = _cli_paragraphs_claiming_mcp_surface(text)
    assert not offenders, (
        "a paragraph shows a `tapps-mcp memory` invocation and also claims the MCP action "
        f"surface; the CLI cannot reach {sorted(_mcp_actions() - _cli_commands())}: {offenders}"
    )


def test_surface_conflation_guard_rejects_both_forms_of_the_defect() -> None:
    """Control for the guard above: it must fire on both shapes seen in review."""
    phrase_form = (
        "For the 7 reachable MCP actions plus `list`/`save` on the\n"
        'CLI, use `uv run tapps-mcp memory search --query "..."`.'
    )
    named_form = "Use `uv run tapps-mcp memory save` to reach `health` and `related`."
    clean = 'Invoke `uv run tapps-mcp memory search --query "..."` or `tapps-mcp memory save`.'
    assert _cli_paragraphs_claiming_mcp_surface(phrase_form) == [phrase_form]
    assert _cli_paragraphs_claiming_mcp_surface(named_form) == [named_form]
    assert _cli_paragraphs_claiming_mcp_surface(clean) == []
