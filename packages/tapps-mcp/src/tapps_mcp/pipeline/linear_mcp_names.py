"""Host-agnostic Linear MCP plugin tool names (TAP-5451 / TAP-5452).

Claude Code / Cursor register the Linear plugin under different MCP server
ids (``plugin_linear_linear``, ``claude_ai_Linear``, …). Hook matchers and
in-hook tool-name guards must accept every known id — and any future id
whose server segment contains ``linear`` — rather than a single hardcoded
prefix.
"""

from __future__ import annotations

from typing import Final

# Server id segments observed across MCP hosts.
LINEAR_PLUGIN_SERVER_IDS: Final[tuple[str, ...]] = (
    "plugin_linear_linear",  # Cursor / Claude marketplace plugin
    "claude_ai_Linear",  # Claude Code hosted Linear integration
)

_LIST_ISSUES: Final[str] = "list_issues"
_SAVE_ISSUE: Final[str] = "save_issue"
_GET_ISSUE: Final[str] = "get_issue"


def linear_plugin_tool_names(leaf: str) -> tuple[str, ...]:
    """Return full MCP tool names for *leaf* across known hosts, plus bare *leaf*."""
    return (*tuple(f"mcp__{sid}__{leaf}" for sid in LINEAR_PLUGIN_SERVER_IDS), leaf)


def linear_plugin_matcher(leaf: str) -> str:
    """Claude Code PreToolUse matcher alternation for a Linear plugin leaf."""
    return "|".join(linear_plugin_tool_names(leaf))


def is_linear_plugin_tool(tool_name: str, leaf: str) -> bool:
    """True if *tool_name* is Linear plugin *leaf* under any known or linear-bearing host."""
    name = tool_name.strip()
    if name == leaf:
        return True
    suffix = f"__{leaf}"
    if not name.startswith("mcp__") or not name.endswith(suffix):
        return False
    middle = name[len("mcp__") : -len(suffix)]
    if middle in LINEAR_PLUGIN_SERVER_IDS:
        return True
    return "linear" in middle.lower()


def bash_case_pattern(leaf: str) -> str:
    """Bash ``case`` pattern arms for known Linear plugin names of *leaf*."""
    return "|".join(linear_plugin_tool_names(leaf))


def powershell_eq_chain(leaf: str, var: str = "$tool") -> str:
    """PowerShell boolean chain: ``$tool -eq 'a' -or $tool -eq 'b' …``."""
    parts = [f"{var} -eq '{name}'" for name in linear_plugin_tool_names(leaf)]
    return " -or ".join(parts)


def linear_plugin_hint_phrasing(leaf: str = _LIST_ISSUES) -> str:
    """Host-agnostic hint text — never pin agents to one ``mcp__…`` prefix."""
    return f"the Linear MCP `{leaf}` tool (server id varies by host)"


def matcher_covers_linear_leaf(matchers: list[str], leaf: str) -> bool:
    """True when any PreToolUse matcher string covers Linear *leaf*."""
    known = set(linear_plugin_tool_names(leaf))
    for raw in matchers:
        if not isinstance(raw, str) or not raw:
            continue
        if raw in known:
            return True
        for arm in raw.split("|"):
            arm = arm.strip()
            if arm in known:
                return True
            if is_linear_plugin_tool(arm, leaf):
                return True
        # Single regex matcher that clearly targets this leaf + Linear.
        if leaf in raw and "linear" in raw.lower():
            return True
    return False


LINEAR_LIST_ISSUES_MATCHER: Final[str] = linear_plugin_matcher(_LIST_ISSUES)
LINEAR_SAVE_ISSUE_MATCHER: Final[str] = linear_plugin_matcher(_SAVE_ISSUE)
LINEAR_GET_ISSUE_MATCHER: Final[str] = linear_plugin_matcher(_GET_ISSUE)

LINEAR_LIST_ISSUES_NAMES: Final[tuple[str, ...]] = linear_plugin_tool_names(_LIST_ISSUES)
LINEAR_SAVE_ISSUE_NAMES: Final[tuple[str, ...]] = linear_plugin_tool_names(_SAVE_ISSUE)


def _sorted_set_literal(names: tuple[str, ...]) -> str:
    """Render *names* as a set literal in a stable order.

    ``repr(set(...))`` orders by hash, which PYTHONHASHSEED randomizes per
    process — so the generated hook body, and therefore its
    ``tapps-mcp-hook-content-sha``, differed between two runs of the same
    generator. That made "deployed copy matches the generator" unverifiable and
    caused spurious hook rewrites on upgrade (TAP-6581).
    """
    return "{" + ", ".join(repr(n) for n in sorted(names)) + "}"


def resolve_linear_host_placeholders(text: str) -> str:
    """Substitute TAP-5452 Linear host-id placeholders (matcher + in-hook guards)."""
    return (
        text.replace("__LINEAR_SAVE_ISSUE_CASE__", bash_case_pattern("save_issue"))
        .replace("__LINEAR_LIST_ISSUES_CASE__", bash_case_pattern("list_issues"))
        .replace("__LINEAR_SAVE_ISSUE_MATCHER__", LINEAR_SAVE_ISSUE_MATCHER)
        .replace("__LINEAR_LIST_ISSUES_MATCHER__", LINEAR_LIST_ISSUES_MATCHER)
        .replace("__LINEAR_SAVE_ISSUE_PS_EQ__", powershell_eq_chain("save_issue"))
        .replace("__LINEAR_LIST_ISSUES_PS_EQ__", powershell_eq_chain("list_issues"))
        .replace(
            "__LINEAR_LIST_ISSUES_NAMES_REPR__",
            _sorted_set_literal(LINEAR_LIST_ISSUES_NAMES),
        )
    )


# Alias kept for older call sites; prefer :func:`resolve_linear_host_placeholders`.
apply_linear_host_placeholders = resolve_linear_host_placeholders


def patch_linear_hook_matchers(config: dict[str, list[dict[str, object]]]) -> None:
    """Resolve matcher placeholders; expand multi-host arms into one entry each.

    Expanding (instead of a single ``a|b|c`` matcher) keeps exact-membership
    checks on ``mcp__plugin_linear_linear__…`` valid and registers every known
    host as its own Claude PreToolUse matcher.
    """
    for event, entries in list(config.items()):
        expanded: list[dict[str, object]] = []
        for entry in entries:
            matcher = entry.get("matcher")
            if not isinstance(matcher, str):
                expanded.append(entry)
                continue
            resolved = resolve_linear_host_placeholders(matcher)
            if "|" not in resolved:
                expanded.append({**entry, "matcher": resolved})
                continue
            for arm in (a.strip() for a in resolved.split("|") if a.strip()):
                expanded.append({**entry, "matcher": arm})
        config[event] = expanded


def resolve_linear_script_map(scripts: dict[str, str]) -> dict[str, str]:
    """Return a copy of *scripts* with Linear host-id placeholders resolved."""
    return {name: resolve_linear_host_placeholders(body) for name, body in scripts.items()}


__all__ = [
    "LINEAR_GET_ISSUE_MATCHER",
    "LINEAR_LIST_ISSUES_MATCHER",
    "LINEAR_LIST_ISSUES_NAMES",
    "LINEAR_PLUGIN_SERVER_IDS",
    "LINEAR_SAVE_ISSUE_MATCHER",
    "LINEAR_SAVE_ISSUE_NAMES",
    "apply_linear_host_placeholders",
    "bash_case_pattern",
    "is_linear_plugin_tool",
    "linear_plugin_hint_phrasing",
    "linear_plugin_matcher",
    "linear_plugin_tool_names",
    "matcher_covers_linear_leaf",
    "patch_linear_hook_matchers",
    "powershell_eq_chain",
    "resolve_linear_host_placeholders",
    "resolve_linear_script_map",
]
