#!/usr/bin/env python3
"""Ground-truth context-floor measurement for the context-efficiency epic (SG0).

Measures the fixed, always-loaded token cost every TappsMCP session pays
before the agent does anything: MCP tool schemas (docstring + JSON Schema
params), skill descriptions, always-loaded Claude Code rules, CLAUDE.md,
MCP server ``instructions=`` blocks, and the ``tapps_session_start`` static
response skeleton.

Everything is measured FROM SOURCE via ``ast`` -- never via a live MCP
handshake. The deployed fleet (``~/.tapps-mcp/current``) is a blue/green
release snapshot; it does not track the workspace tree, so a live handshake
would silently measure stale code. This script is the single ground-truth
artifact for the epic: both the executor and independent verifiers run this
exact file and compare against the same recorded baseline.

Measurement logic lives in the ``context_floor_*.py`` modules alongside this
file (``context_floor_core`` for shared AST/path primitives, then one module
per bucket -- ``_tools``, ``_skills``, ``_rules``, ``_server``,
``_session_start`` -- assembled by ``context_floor_report.build_report()``).
Mirrors this directory's ``tool_budget_lint.py`` / ``check-tool-budget.py``
split (heavy logic in importable modules, thin argparse wrapper here); split
further into one module per bucket because the combined logic was too large
for one file to stay maintainable (radon MI collapses well before 1,000
lines) -- import the same way ``check-tool-budget.py`` imports
``tool_budget_lint``.

Token estimator (fixed -- do not substitute tiktoken or any other tokenizer):
    tokens(text) = round(len(text.encode("utf-8")) / 4)
This reproduces the project's recorded baseline; changing it invalidates
every number in this file's self-check and the epic's contract.

Usage:
    python3 scripts/measure_context_floor.py            # readable table
    python3 scripts/measure_context_floor.py --json      # machine-readable
    python3 scripts/measure_context_floor.py --skills    # per-skill table
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from context_floor_core import MeasurementError
from context_floor_report import build_report


def print_table(report: dict[str, Any]) -> None:
    rows = [
        ("tool_schema_tokens", report["tool_schema_tokens"]),
        ("  tool_docstring_tokens", report["tool_docstring_tokens"]),
        ("  tool_param_tokens", report["tool_param_tokens"]),
        ("tool_count", report["tool_count"]),
        ("skill_description_tokens", report["skill_description_tokens"]),
        ("always_loaded_rule_tokens", report["always_loaded_rule_tokens"]),
        ("claude_md_tokens", report["claude_md_tokens"]),
        ("server_instruction_tokens", report["server_instruction_tokens"]),
        ("session_start_tokens", report["session_start_tokens"]),
        ("floor_tokens", report["floor_tokens"]),
    ]
    width = max(len(name) for name, _ in rows)
    print("TappsMCP context floor (measured from source)")
    print("-" * (width + 12))
    for name, value in rows:
        print(f"{name:<{width}}  {value:>8,}")
    over_400 = report["detail"]["tools"]["docstrings_over_400_bytes"]
    total_tools = report["detail"]["tools"]["total_tool_count"]
    print(f"\n{over_400} of {total_tools} tool docstrings exceed 400 bytes")


def print_skills_table(report: dict[str, Any]) -> None:
    skills = report["detail"]["skills"]
    print(f"{'skill':<28}{'bytes':>8}{'tokens':>8}  fork  disable-invoke")
    print("-" * 66)
    for entry in skills:
        fork = "yes" if entry["context_fork"] else ""
        disable = "yes" if entry["disable_model_invocation"] else ""
        print(
            f"{entry['name']:<28}{entry['description_bytes']:>8}{entry['description_tokens']:>8}"
            f"  {fork:<4}  {disable}"
        )
    total_bytes = sum(e["description_bytes"] for e in skills)
    total_tokens = sum(e["description_tokens"] for e in skills)
    print("-" * 66)
    print(f"{len(skills)} skills, {total_bytes} bytes, {total_tokens} tokens total")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--json", action="store_true", help="print the full machine-readable report as JSON"
    )
    parser.add_argument(
        "--skills", action="store_true", help="print the per-skill description breakdown"
    )
    args = parser.parse_args()

    try:
        report = build_report()
    except MeasurementError as exc:
        print(f"measurement failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    if args.skills:
        print_skills_table(report)
        return 0
    print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
