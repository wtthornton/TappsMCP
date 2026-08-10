"""Tool-budget lint: new-registration gate and documented-count check.

Two checks share this module:

* :func:`check_new_registrations` — a PR that adds an MCP tool registration
  must also touch ``docs/architecture/tool-budget.md`` (TAP-2029).
* :func:`check_documented_counts` — the per-server tool counts printed in the
  front-door docs must match the registry (TAP-5611). They had drifted twice
  (TAP-4577 first) because nothing enforced them.

``scripts/check-tool-budget.py`` is the CLI entry point. The logic lives here
so it is importable under a valid module name and testable from pytest.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

# Pattern that marks a new MCP tool registration line in a diff. Both servers
# register through the register_tool() helper; the bare @mcp.tool() decorator
# is still matched so a direct registration cannot slip past.
_NEW_TOOL_RE = re.compile(r"^\+[^+].*(?:@mcp\.tool\s*\(|\bregister_tool\s*\()")

# Same shape on the removal side. Registrations that move between modules
# during a refactor appear as both an add and a delete; counting only the adds
# reported every module split as N brand-new tools (TAP-5733).
_REMOVED_TOOL_RE = re.compile(r"^-[^-].*(?:@mcp\.tool\s*\(|\bregister_tool\s*\()")

# Unified-diff file header, used to scope the scan to package source. Test
# fixtures legitimately contain `register_tool(` strings; counting those would
# make the lint fire on its own tests.
_DIFF_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Where the tools are registered, and the module that defines the helper (whose
# own `def register_tool(` must not be counted as a registration).
_PACKAGES: dict[str, Path] = {
    "tapps-mcp": Path("packages/tapps-mcp/src/tapps_mcp"),
    "docs-mcp": Path("packages/docs-mcp/src/docs_mcp"),
}
_REGISTER_HELPER = "mcp_register.py"
_REGISTER_CALL_RE = re.compile(r"\bregister_tool\s*\(")

# Front-door docs that print per-server tool counts.
_COUNT_DOCS = ("README.md", "CLAUDE.md", "docs/ARCHITECTURE.md")

# "(44 tools)" — attributed to a server by the nearest name on the line, or
# positionally against the previous line for the ASCII dependency diagram.
_TOOL_COUNT_RE = re.compile(r"\((\d+) tools\)")
# "**86 tools** (44 TappsMCP + 42 DocsMCP)" and its wordier variants.
_COMBINED_COUNT_RE = re.compile(r"\*\*(\d+)[^*]*tools\*\*\s*\((\d+) TappsMCP \+ (\d+) DocsMCP\)")
_SERVER_NAME_RES: dict[str, re.Pattern[str]] = {
    "tapps-mcp": re.compile(r"tapps-mcp|TappsMCP|tapps_mcp"),
    "docs-mcp": re.compile(r"docs-mcp|DocsMCP|docs_mcp"),
}

# The budget doc that must be touched when a new tool is added.
_BUDGET_DOC = "docs/architecture/tool-budget.md"

# Bypass token in commit message (case-insensitive).
_BYPASS_RE = re.compile(r"Tool-Budget\s*:\s*(deferred|skip)", re.IGNORECASE)


def get_diff(diff_range: str) -> str:
    """Return the unified diff text for diff_range."""
    result = subprocess.run(
        ["git", "diff", diff_range],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_changed_files(diff_range: str) -> list[str]:
    """Return list of file paths touched in diff_range."""
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_package_source(path: str) -> bool:
    """True when *path* is a package source file (not a test, not a script)."""
    return any(path.startswith(f"{prefix}/") for prefix in map(str, _PACKAGES.values()))


def _count_registrations(diff_text: str, pattern: re.Pattern[str]) -> int:
    """Count package-source lines in *diff_text* matching *pattern*.

    Scoped by file: a `register_tool(` literal inside a test fixture or inside
    this lint's own source is not a registration, and counting it would make
    the check fire on the very PR that adds a test for it.
    """
    count = 0
    in_source = False
    for line in diff_text.splitlines():
        header = _DIFF_HEADER_RE.match(line)
        if header:
            in_source = _is_package_source(header.group(1))
            continue
        if in_source and pattern.match(line):
            count += 1
    return count


def count_added_registrations(diff_text: str) -> int:
    """Count added tool registrations in package source within a unified diff."""
    return _count_registrations(diff_text, _NEW_TOOL_RE)


def count_removed_registrations(diff_text: str) -> int:
    """Count removed tool registrations in package source within a unified diff."""
    return _count_registrations(diff_text, _REMOVED_TOOL_RE)


def count_net_new_registrations(diff_text: str) -> int:
    """Registrations added minus registrations removed, floored at zero.

    A tool moved between modules is deleted from one file and added to another,
    so the raw added-count alone reports every module split as N brand-new
    tools. Netting the two makes a pure move a no-op while still catching a
    genuine addition (TAP-5733).
    """
    net = count_added_registrations(diff_text) - count_removed_registrations(diff_text)
    return max(net, 0)


def check_new_registrations(
    diff_text: str, changed_files: list[str], commit_msg: str
) -> tuple[bool, str]:
    """Return (ok, reason).

    ok=True  → no action needed
    ok=False → fail with reason
    """
    # 1. Bypass via commit message or env var.
    bypass_env = os.environ.get("TOOL_BUDGET_BYPASS", "")
    if _BYPASS_RE.search(commit_msg) or _BYPASS_RE.search(bypass_env):
        return True, "bypass token found — skipping check"

    # 2. Count net-new registration lines in package source. Moves between
    #    modules cancel out; only a genuine addition survives.
    count = count_net_new_registrations(diff_text)
    if not count:
        return True, "no net-new tool registrations in package source"

    noun = "tool" if count == 1 else "tools"

    # 3. Verify the budget doc was also updated.
    if _BUDGET_DOC in changed_files:
        return True, f"{count} new {noun} added and tool-budget.md updated"

    # 4. Fail.
    reason = textwrap.dedent(f"""\
        {count} new MCP {noun} registered but {_BUDGET_DOC} was not updated.

        When adding a new @mcp.tool() handler, update docs/architecture/tool-budget.md
        to document whether the tool is eager (counts against the 20-tool budget) or
        deferred (tool_search only). See the "Known server tool counts" table.

        To bypass for exceptional cases, add to your commit message:
            Tool-Budget: deferred   # or: Tool-Budget: skip
    """)
    return False, reason


def count_registered_tools(root: Path = _REPO_ROOT) -> dict[str, int]:
    """Return the registered tool count per package, straight from the source."""
    counts: dict[str, int] = {}
    for server, rel in _PACKAGES.items():
        total = 0
        for path in sorted((root / rel).rglob("*.py")):
            if path.name == _REGISTER_HELPER:
                continue
            total += len(_REGISTER_CALL_RE.findall(path.read_text(encoding="utf-8")))
        counts[server] = total
    return counts


def _servers_on_line(line: str) -> list[tuple[int, str]]:
    """Return (column, server) for every server name mentioned in *line*."""
    found = [
        (m.start(), server)
        for server, pattern in _SERVER_NAME_RES.items()
        for m in pattern.finditer(line)
    ]
    return sorted(found)


def _attribute_counts(lines: list[str], index: int) -> list[tuple[str, int]]:
    """Attribute each ``(N tools)`` on ``lines[index]`` to a server.

    Names usually sit on the same line. The package dependency diagram puts
    them on the line above instead, so fall back to positional pairing there.
    """
    line = lines[index]
    matches = list(_TOOL_COUNT_RE.finditer(line))
    if not matches:
        return []
    names = _servers_on_line(line)
    if not names:
        prev = next((lines[i] for i in range(index - 1, -1, -1) if lines[i].strip()), "")
        names = _servers_on_line(prev)
        if len(names) != len(matches):
            return []
        return [(server, int(m.group(1))) for (_col, server), m in zip(names, matches, strict=True)]

    attributed: list[tuple[str, int]] = []
    for match in matches:
        before = [n for n in names if n[0] < match.start()]
        _col, server = before[-1] if before else names[0]
        attributed.append((server, int(match.group(1))))
    return attributed


def _per_server_mismatches(
    doc: str, lines: list[str], index: int, actual: dict[str, int]
) -> list[str]:
    """Report every ``(N tools)`` on one line that disagrees with the registry."""
    return [
        f"{doc}:{index + 1} claims {claimed} {server} tools (registry has {actual[server]})"
        for server, claimed in _attribute_counts(lines, index)
        if claimed != actual[server]
    ]


def _combined_mismatches(doc: str, line: str, index: int, actual: dict[str, int]) -> list[str]:
    """Report every ``**N tools** (A TappsMCP + B DocsMCP)`` claim that is wrong."""
    found: list[str] = []
    for combined in _COMBINED_COUNT_RE.finditer(line):
        total, tapps, docs = (int(group) for group in combined.groups())
        if tapps != actual["tapps-mcp"] or docs != actual["docs-mcp"]:
            found.append(
                f"{doc}:{index + 1} claims {tapps} + {docs} "
                f"(registry has {actual['tapps-mcp']} + {actual['docs-mcp']})"
            )
        elif total != tapps + docs:
            found.append(f"{doc}:{index + 1} totals {total} but {tapps} + {docs} = {tapps + docs}")
    return found


def check_documented_counts(root: Path = _REPO_ROOT) -> tuple[bool, str]:
    """Verify every documented tool count matches the registry."""
    actual = count_registered_tools(root)
    mismatches: list[str] = []

    for doc in _COUNT_DOCS:
        path = root / doc
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            mismatches.extend(_per_server_mismatches(doc, lines, index, actual))
            mismatches.extend(_combined_mismatches(doc, line, index, actual))

    if mismatches:
        listed = "\n  ".join(mismatches)
        return False, textwrap.dedent(
            f"""\
            Documented tool counts disagree with the registry:

              {listed}

            The registry is the source of truth — it counts register_tool()
            call sites per package. Update the docs, not this check.
            """
        )
    summary = ", ".join(f"{server} {count}" for server, count in sorted(actual.items()))
    return True, f"documented counts match the registry ({summary})"


def run_self_tests() -> None:
    """Self-test: verify pass/fail paths with synthetic fixtures."""
    print("Running self-tests…")

    # --- PASS fixtures ---

    # Pass: no new tools in diff
    ok, msg = check_new_registrations("", [], "")
    assert ok, f"Expected PASS for empty diff, got: {msg}"
    print("  PASS: empty diff → ok")

    # Pass: new tool BUT budget doc updated
    src_header = "+++ b/packages/tapps-mcp/src/tapps_mcp/server.py\n"
    diff_with_tool = src_header + "+    @mcp.tool()\n+    async def my_new_tool() -> None: ...\n"
    ok, msg = check_new_registrations(
        diff_with_tool, [_BUDGET_DOC, "packages/tapps-mcp/src/server.py"], ""
    )
    assert ok, f"Expected PASS when budget doc updated, got: {msg}"
    print("  PASS: new tool + budget doc updated → ok")

    # Pass: bypass token in commit message
    ok, msg = check_new_registrations(
        diff_with_tool, [], "feat: add tool\n\nTool-Budget: deferred\n"
    )
    assert ok, f"Expected PASS with bypass token, got: {msg}"
    print("  PASS: bypass token in commit message → ok")

    # Pass: bypass env var
    os.environ["TOOL_BUDGET_BYPASS"] = "Tool-Budget: skip"
    ok, msg = check_new_registrations(diff_with_tool, [], "")
    del os.environ["TOOL_BUDGET_BYPASS"]
    assert ok, f"Expected PASS with bypass env var, got: {msg}"
    print("  PASS: bypass env var → ok")

    # Pass: tool moved between modules — deleted from one file, added to
    # another. Net zero, so a module split must not read as a new tool.
    moved_header = "+++ b/packages/tapps-mcp/src/tapps_mcp/server_system_tools.py\n"
    moved = (
        src_header
        + "-    register_tool(mcp_instance, tapps_moved, annotations=_ANN)\n"
        + moved_header
        + "+    register_tool(mcp_instance, tapps_moved, annotations=_ANN)\n"
    )
    ok, msg = check_new_registrations(moved, ["packages/tapps-mcp/src/tapps_mcp/server.py"], "")
    assert ok, f"Expected PASS for a moved registration, got: {msg}"
    print("  PASS: registration moved between modules → ok")

    # --- FAIL fixtures ---

    # Fail: new tool, budget doc NOT updated, no bypass
    ok, msg = check_new_registrations(diff_with_tool, ["packages/tapps-mcp/src/server.py"], "")
    assert not ok, "Expected FAIL when budget doc not updated"
    assert _BUDGET_DOC in msg, "Expected budget doc path in failure message"
    print("  FAIL: new tool, budget doc missing → correctly rejected")

    # Fail: two new tools, no budget doc
    two_tools = src_header + (
        "+    @mcp.tool()\n+    async def tool_one() -> None: ...\n"
        "+    @mcp.tool(description='...')\n+    async def tool_two() -> None: ...\n"
    )
    ok, msg = check_new_registrations(two_tools, [], "")
    assert not ok, "Expected FAIL for two tools without budget update"
    assert "2 new" in msg, f"Expected '2 new' in message, got: {msg}"
    print("  FAIL: two new tools, no budget doc → correctly rejected")

    # Fail: register_tool() is the real registration path (TAP-5611) — the
    # decorator-only pattern was blind to every tool added since TAP-1963.
    register_line = "+    register_tool(mcp_instance, tapps_new_thing, annotations=_ANN)\n"
    ok, msg = check_new_registrations(src_header + register_line, [], "")
    assert not ok, "Expected FAIL for a new register_tool() call"
    print("  FAIL: new register_tool() call, no budget doc → correctly rejected")

    # Pass: the same line inside a test fixture is not a registration.
    test_header = "+++ b/packages/tapps-mcp/tests/unit/test_tool_budget_lint.py\n"
    ok, msg = check_new_registrations(test_header + register_line, [], "")
    assert ok, f"Expected PASS for a register_tool string in a test, got: {msg}"
    print("  PASS: register_tool() inside a test fixture → not counted")

    # Fail: a genuine addition alongside a move still nets one new tool, so
    # netting must not become a way to smuggle a tool in behind a refactor.
    move_plus_add = (
        src_header
        + "-    register_tool(mcp_instance, tapps_moved, annotations=_ANN)\n"
        + moved_header
        + "+    register_tool(mcp_instance, tapps_moved, annotations=_ANN)\n"
        + "+    register_tool(mcp_instance, tapps_brand_new, annotations=_ANN)\n"
    )
    ok, msg = check_new_registrations(move_plus_add, [], "")
    assert not ok, "Expected FAIL when a move is paired with a real addition"
    assert "1 new" in msg, f"Expected '1 new' in message, got: {msg}"
    print("  FAIL: move + one genuine addition → correctly rejected")

    print("All self-tests passed.")
