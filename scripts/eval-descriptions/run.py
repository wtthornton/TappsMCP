#!/usr/bin/env python3
"""Run tool-selection eval scenarios against a tapps-mcp install.

For each scenario in scenarios.yaml, invokes a fresh `claude -p` agent
with the live MCP tool catalog loaded, parses the stream-json output to
find the first MCP tool call, and scores against the expected tool.

Uses Claude CLI for auth (OAuth) and cost (subscription / Max plan).
No ANTHROPIC_API_KEY plumbing required.

Usage:
    # Run against current tree, write results to /tmp/eval-HEAD.json
    python3 scripts/eval-descriptions/run.py --output /tmp/eval-HEAD.json

    # Run a subset of scenarios (smoke test)
    python3 scripts/eval-descriptions/run.py --only lookup_docs_async_httpx,quick_check_after_edit

    # Custom MCP config (e.g., for a baseline worktree)
    python3 scripts/eval-descriptions/run.py --mcp-config /path/to/baseline/.mcp.json

The output JSON shape is consumed by compare.py and report.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 — we invoke `claude` with explicit, hard-coded args.
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.yaml"

# Built-in Claude tools the eval-mode agent is NOT allowed to call. Forces
# the agent to make a tool decision from the MCP catalog or nothing.
# (TodoWrite is kept allowed — we want the agent free to plan internally.)
_DISALLOWED_BUILTINS = ["Edit", "Write", "Bash", "NotebookEdit", "WebFetch", "WebSearch"]

# How long a single scenario is allowed to run before we kill it. Cold-start
# can spend 30-50s on MCP server spawn + uv venv resolution; 240s leaves
# headroom for that plus the agent step without inflating the noise floor.
_SCENARIO_TIMEOUT_SECONDS = 240

# Cap on the pre-warm dummy invocation. Pre-warm timing-out is not fatal —
# it just means the first real scenario eats whatever latency we tried to
# absorb. Set generously so the warm-up genuinely completes one MCP handshake.
_PREWARM_TIMEOUT_SECONDS = 120

_SYSTEM_PROMPT = """\
You are an evaluator for the tapps-mcp tool catalog. Your job is to pick \
the single most appropriate tool for the user's stated intent and CALL IT \
immediately with reasonable placeholder arguments (e.g. `file_path="src/foo.py"`, \
`library="httpx"`, etc.). Make exactly ONE tool call, then stop. Do not chain \
calls. Do not ask the user for clarification — pick the best fit from the \
catalog and proceed. The arguments are not what we are evaluating; the tool \
choice is.
"""


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    expected_tool: str
    acceptable_alternatives: list[str]
    actual_tool: str | None
    verdict: str  # "exact" | "acceptable" | "wrong" | "no_tool" | "error"
    elapsed_ms: int
    error: str | None = None
    raw_events_path: str | None = None


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    scenarios = data.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise ValueError("scenarios.yaml has no top-level `scenarios:` list")
    return scenarios


def first_mcp_tool_call(stream_events: list[dict[str, Any]]) -> str | None:
    """Return the name of the first tool_use event where the tool is an MCP tool.

    MCP tool names start with `mcp__` per Claude Code's naming convention.
    Built-in tools (TodoWrite, etc.) are ignored — we only care about MCP picks.
    """
    for event in stream_events:
        msg = event.get("message") or event
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = str(block.get("name", ""))
                if name.startswith("mcp__"):
                    return name
    return None


def score(expected: str, alternatives: list[str], actual: str | None) -> str:
    if actual is None:
        return "no_tool"
    if actual == expected:
        return "exact"
    if actual in alternatives:
        return "acceptable"
    return "wrong"


def run_scenario(
    scenario: dict[str, Any],
    *,
    mcp_config: Path | None,
    cwd: Path,
    raw_output_dir: Path,
) -> ScenarioResult:
    sid = scenario["id"]
    prompt = scenario["prompt"]
    expected = scenario["expected_tool"]
    alternatives = scenario.get("acceptable_alternatives") or []
    category = scenario.get("category", "uncategorized")

    cmd: list[str] = [
        "claude",
        "-p",
        prompt,
        "--output-format=stream-json",
        "--include-partial-messages",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--system-prompt",
        _SYSTEM_PROMPT,
        "--disallowed-tools",
        *_DISALLOWED_BUILTINS,
        "--verbose",
    ]
    if mcp_config is not None:
        cmd.extend(["--strict-mcp-config", "--mcp-config", str(mcp_config)])

    start = time.perf_counter()
    raw_events: list[dict[str, Any]] = []
    raw_path = raw_output_dir / f"{sid}.jsonl"

    try:
        proc = subprocess.run(  # nosec B603 — explicit `claude` args, no shell, no user input.
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_SCENARIO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ScenarioResult(
            scenario_id=sid,
            category=category,
            expected_tool=expected,
            acceptable_alternatives=alternatives,
            actual_tool=None,
            verdict="error",
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            error=f"scenario exceeded {_SCENARIO_TIMEOUT_SECONDS}s",
            raw_events_path=str(raw_path) if raw_path.exists() else None,
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # Persist raw stream for debugging.
    raw_path.write_text(proc.stdout, encoding="utf-8")

    if proc.returncode != 0:
        return ScenarioResult(
            scenario_id=sid,
            category=category,
            expected_tool=expected,
            acceptable_alternatives=alternatives,
            actual_tool=None,
            verdict="error",
            elapsed_ms=elapsed_ms,
            error=f"claude -p exit {proc.returncode}: {proc.stderr[:500]}",
            raw_events_path=str(raw_path),
        )

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw_events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    actual = first_mcp_tool_call(raw_events)
    return ScenarioResult(
        scenario_id=sid,
        category=category,
        expected_tool=expected,
        acceptable_alternatives=alternatives,
        actual_tool=actual,
        verdict=score(expected, alternatives, actual),
        elapsed_ms=elapsed_ms,
        raw_events_path=str(raw_path),
    )


def prewarm_mcp(mcp_config: Path | None, cwd: Path) -> int:
    """Spawn one throwaway `claude -p` invocation to warm MCP servers before
    the timed scenario loop.

    `claude -p` re-spawns each MCP server on every invocation, but the
    uv-managed venv, Python `.pyc` bytecode cache, and OS filesystem cache
    persist across invocations within the same worktree. Pre-warming pulls
    those one-time costs out of the first real scenario's 240s budget,
    cutting cold-start timeouts to near-zero.

    The dummy prompt is intentionally trivial ("ping") and built-in tools
    are disallowed so the agent cannot accidentally do useful work that
    would skew downstream scenarios.

    Returns elapsed milliseconds (best-effort, capped at the timeout).
    """
    if mcp_config is None:
        return 0
    cmd: list[str] = [
        "claude",
        "-p",
        "ping",
        "--output-format=stream-json",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--disallowed-tools",
        *_DISALLOWED_BUILTINS,
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp_config),
        "--verbose",
    ]
    start = time.perf_counter()
    try:
        subprocess.run(  # nosec B603 — explicit `claude` args, no shell.
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_PREWARM_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    return int((time.perf_counter() - start) * 1000)


_VERDICT_COLORS: dict[str, str] = {
    "exact": "\033[32m",       # green
    "acceptable": "\033[33m",  # yellow
    "wrong": "\033[31m",       # red
    "no_tool": "\033[31m",
    "error": "\033[35m",       # magenta
}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", "-o", type=Path,
        default=Path(tempfile.gettempdir()) / "eval-results.json",
        help="Where to write the per-scenario results JSON.",
    )
    parser.add_argument(
        "--mcp-config", type=Path, default=None,
        help="Path to .mcp.json to pass via --mcp-config (default: claude CLI defaults).",
    )
    parser.add_argument(
        "--cwd", type=Path, default=REPO_ROOT,
        help="Working directory to run `claude -p` from (default: repo root).",
    )
    parser.add_argument(
        "--only", type=str, default="",
        help="Comma-separated scenario ids to run (default: all).",
    )
    parser.add_argument(
        "--ref-label", type=str, default="",
        help="Optional label to include in results (e.g. 'HEAD', 'baseline-cc1d340').",
    )
    return parser


def _filter_scenarios(scenarios: list[dict[str, Any]], only: str) -> list[dict[str, Any]]:
    if not only:
        return scenarios
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    return [s for s in scenarios if s["id"] in wanted]


def _print_progress(i: int, total: int, scenario_id: str, result: ScenarioResult) -> None:
    color = _VERDICT_COLORS.get(result.verdict, "")
    reset = "\033[0m"
    print(
        f"  [{i}/{total}] {scenario_id}... {color}{result.verdict}{reset}"
        f" ({result.elapsed_ms}ms, actual={result.actual_tool})",
        file=sys.stderr,
        flush=True,
    )


_VERDICT_NAMES: tuple[str, ...] = ("exact", "acceptable", "wrong", "no_tool", "error")
_LENIENT_PASS: frozenset[str] = frozenset(("exact", "acceptable"))


def build_summary(
    results: list[ScenarioResult],
    *,
    ref_label: str,
    cwd: Path,
    mcp_config: Path | None,
) -> dict[str, Any]:
    n = max(len(results), 1)
    verdict_counts = {v: 0 for v in _VERDICT_NAMES}
    n_strict = 0
    n_lenient = 0
    for r in results:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
        if r.verdict == "exact":
            n_strict += 1
        if r.verdict in _LENIENT_PASS:
            n_lenient += 1
    return {
        "ref_label": ref_label,
        "cwd": str(cwd),
        "mcp_config": str(mcp_config) if mcp_config else None,
        "total": len(results),
        "by_verdict": verdict_counts,
        "accuracy_strict": n_strict / n,
        "accuracy_lenient": n_lenient / n,
        "results": [asdict(r) for r in results],
    }


def main() -> int:
    args = _build_arg_parser().parse_args()
    scenarios = _filter_scenarios(load_scenarios(), args.only)
    if not scenarios:
        print(f"No scenarios matched --only={args.only}", file=sys.stderr)
        return 1

    raw_dir = args.output.parent / f"{args.output.stem}-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    mcp_hint = f" with MCP config {args.mcp_config}" if args.mcp_config else ""
    print(f"Running {len(scenarios)} scenarios against {args.cwd}{mcp_hint}...", file=sys.stderr)

    if args.mcp_config is not None:
        print("  Pre-warming MCP servers (dummy `claude -p ping`)...", file=sys.stderr)
        warm_ms = prewarm_mcp(args.mcp_config, args.cwd)
        print(f"  Pre-warm done in {warm_ms}ms.", file=sys.stderr)

    results: list[ScenarioResult] = []
    for i, scenario in enumerate(scenarios, 1):
        r = run_scenario(scenario, mcp_config=args.mcp_config, cwd=args.cwd, raw_output_dir=raw_dir)
        results.append(r)
        _print_progress(i, len(scenarios), scenario["id"], r)

    summary = build_summary(
        results, ref_label=args.ref_label, cwd=args.cwd, mcp_config=args.mcp_config,
    )
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"\nSummary: strict={summary['accuracy_strict']:.1%} "
        f"lenient={summary['accuracy_lenient']:.1%} ({summary['by_verdict']})",
        file=sys.stderr,
    )
    print(f"Results: {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
