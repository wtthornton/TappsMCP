#!/usr/bin/env python3
"""Run tool-selection eval scenarios against a tapps-mcp install.

For each scenario in scenarios.yaml, invokes a fresh `claude -p` agent
with the live MCP tool catalog loaded, parses the stream-json output to
find the first MCP tool call, and scores against the expected tool.

Two backends:

* ``--backend=cli`` (default): subprocess ``claude -p`` per scenario. Uses
  Claude CLI OAuth (Max-plan subscription); no ``ANTHROPIC_API_KEY``
  required, but subject to the Max-plan rate limit (~130 calls per hour
  window). Local-dev default.
* ``--backend=api``: Anthropic Messages API directly via the ``anthropic``
  Python SDK (lazy-imported). Spawns one tapps-mcp stdio session per run,
  lists tools, and calls ``messages.create()`` with ``tools=`` per
  scenario. Needs ``ANTHROPIC_API_KEY``. Bills per-token (~$0.01–0.03 per
  scenario at Sonnet 4.6). Rate-limit-immune; this is the CI backend
  ([.github/workflows/eval-descriptions.yml](../../.github/workflows/eval-descriptions.yml)).

Usage:
    # Run against current tree, write results to /tmp/eval-HEAD.json
    python3 scripts/eval-descriptions/run.py --output /tmp/eval-HEAD.json

    # Run a subset of scenarios (smoke test)
    python3 scripts/eval-descriptions/run.py --only lookup_docs_async_httpx,quick_check_after_edit

    # Custom MCP config (e.g., for a baseline worktree)
    python3 scripts/eval-descriptions/run.py --mcp-config /path/to/baseline/.mcp.json

    # CI backend (Anthropic API, needs ANTHROPIC_API_KEY)
    python3 scripts/eval-descriptions/run.py --backend=api --output /tmp/eval-HEAD.json

The output JSON shape is consumed by compare.py and report.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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
    """Outcome of a single tool-selection eval scenario."""

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
    """Load eval scenario definitions from a YAML file."""
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
    """Map expected vs actual MCP tool name to an eval verdict string."""
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
    """Invoke `claude -p` for one scenario and score the first MCP tool call."""
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


# ---------------------------------------------------------------------------
# API backend (Anthropic Messages API direct)
# ---------------------------------------------------------------------------

# Default model for ``--backend=api``. Sonnet 4.6 is the right cost/quality
# point for first-call selection: comparable selection accuracy to Opus on
# this corpus at ~10x lower per-token cost.
_API_DEFAULT_MODEL = "claude-sonnet-4-6"

# Per-scenario API timeout. The API is fast (typically <5s); set
# generously so transient slow responses don't false-fail.
_API_SCENARIO_TIMEOUT_SECONDS = 60


def _expand_env(env_dict: dict[str, str] | None) -> dict[str, str]:
    """Expand ``${VAR}`` references in a .mcp.json env block.

    Falls back to the parent process env for unset variables (same shape as
    Claude Code's .mcp.json substitution).
    """
    if not env_dict:
        return {}
    return {k: os.path.expandvars(v) for k, v in env_dict.items()}


def _load_tapps_mcp_server_config(mcp_config: Path) -> dict[str, Any]:
    """Read the tapps-mcp server entry from a .mcp.json."""
    with mcp_config.open(encoding="utf-8") as f:
        cfg = json.load(f)
    servers = cfg.get("mcpServers", {})
    server = servers.get("tapps-mcp")
    if server is None:
        raise ValueError(f"{mcp_config} has no mcpServers.tapps-mcp entry")
    return server


async def _run_scenarios_api(
    scenarios: list[dict[str, Any]],
    *,
    mcp_config: Path,
    cwd: Path,
    raw_output_dir: Path,
    model: str,
) -> list[ScenarioResult]:
    """Run scenarios via Anthropic Messages API (rate-limit-immune backend).

    Spawns one tapps-mcp stdio session, lists its tools, and calls
    ``messages.create()`` per scenario with the catalog. Captures the
    first ``tool_use`` block as the agent's choice. Tool names are
    prefixed with ``mcp__tapps-mcp__`` so they match ``scenarios.yaml``
    ``expected_tool`` values without modification.
    """
    try:
        from anthropic import AsyncAnthropic  # noqa: PLC0415
        from mcp import ClientSession  # noqa: PLC0415
        from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "--backend=api requires the `anthropic` and `mcp` Python SDKs. "
            "Run `uv sync --all-packages` (anthropic is in [tool.uv.dev-dependencies])."
        ) from exc

    server_cfg = _load_tapps_mcp_server_config(mcp_config)
    server_params = StdioServerParameters(
        command=server_cfg["command"],
        args=list(server_cfg.get("args", [])),
        env={**os.environ, **_expand_env(server_cfg.get("env"))},
        cwd=str(cwd),
    )

    anthropic_client = AsyncAnthropic()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()
            tools_result = await mcp_client.list_tools()

            api_tools: list[dict[str, Any]] = [
                {
                    "name": f"mcp__tapps-mcp__{t.name}",
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in tools_result.tools
            ]
            print(
                f"  API backend: loaded {len(api_tools)} tools from tapps-mcp catalog",
                file=sys.stderr,
            )

            results: list[ScenarioResult] = []
            for i, scenario in enumerate(scenarios, 1):
                r = await _run_scenario_api(
                    scenario,
                    anthropic_client=anthropic_client,
                    api_tools=api_tools,
                    raw_output_dir=raw_output_dir,
                    model=model,
                )
                _print_progress(i, len(scenarios), scenario["id"], r)
                results.append(r)
            return results


async def _run_scenario_api(
    scenario: dict[str, Any],
    *,
    anthropic_client: Any,
    api_tools: list[dict[str, Any]],
    raw_output_dir: Path,
    model: str,
) -> ScenarioResult:
    """Run a single scenario via ``messages.create()``; score the first tool_use."""
    sid = scenario["id"]
    prompt = scenario["prompt"]
    expected = scenario["expected_tool"]
    alternatives = scenario.get("acceptable_alternatives") or []
    category = scenario.get("category", "uncategorized")

    start = time.perf_counter()
    raw_path = raw_output_dir / f"{sid}.json"
    try:
        response = await asyncio.wait_for(
            anthropic_client.messages.create(
                model=model,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                tools=api_tools,
            ),
            timeout=_API_SCENARIO_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return ScenarioResult(
            scenario_id=sid,
            category=category,
            expected_tool=expected,
            acceptable_alternatives=alternatives,
            actual_tool=None,
            verdict="error",
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            error=f"API call exceeded {_API_SCENARIO_TIMEOUT_SECONDS}s",
        )
    except Exception as exc:  # noqa: BLE001 — surface any API error verbatim
        return ScenarioResult(
            scenario_id=sid,
            category=category,
            expected_tool=expected,
            acceptable_alternatives=alternatives,
            actual_tool=None,
            verdict="error",
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    # Persist a serializable view of the response for debugging.
    try:
        raw_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    except (OSError, AttributeError):
        pass

    actual: str | None = None
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use":
            name = getattr(block, "name", "")
            if name.startswith("mcp__"):
                actual = name
                break

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
    parser.add_argument(
        "--backend",
        type=str,
        default="cli",
        choices=("cli", "api"),
        help=(
            "cli (default): subprocess `claude -p` per scenario via Max-plan "
            "OAuth. api: Anthropic Messages API direct (needs ANTHROPIC_API_KEY); "
            "rate-limit-immune CI backend."
        ),
    )
    parser.add_argument(
        "--model", type=str, default=_API_DEFAULT_MODEL,
        help=(
            f"Model for --backend=api (default: {_API_DEFAULT_MODEL}). "
            "Ignored for --backend=cli (uses whatever Claude CLI is configured for)."
        ),
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
    """Aggregate per-scenario verdicts into a JSON-serializable summary."""
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
    """CLI entry: run eval scenarios and write JSON results."""
    args = _build_arg_parser().parse_args()
    scenarios = _filter_scenarios(load_scenarios(), args.only)
    if not scenarios:
        print(f"No scenarios matched --only={args.only}", file=sys.stderr)
        return 1

    raw_dir = args.output.parent / f"{args.output.stem}-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    mcp_hint = f" with MCP config {args.mcp_config}" if args.mcp_config else ""
    print(
        f"Running {len(scenarios)} scenarios against {args.cwd}{mcp_hint} "
        f"(backend={args.backend})...",
        file=sys.stderr,
    )

    if args.backend == "api":
        if args.mcp_config is None:
            print(
                "--backend=api requires --mcp-config (used to spawn the "
                "tapps-mcp stdio server for tool catalog discovery).",
                file=sys.stderr,
            )
            return 1
        # Auth: prefer ANTHROPIC_AUTH_TOKEN (Max-plan OAuth bearer; same
        # credential Claude Code uses) over ANTHROPIC_API_KEY (paid API).
        # The anthropic SDK reads either env var automatically; we just
        # need at least one to be present.
        has_auth = bool(
            os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        if not has_auth:
            print(
                "--backend=api requires either ANTHROPIC_AUTH_TOKEN "
                "(Max-plan OAuth, preferred) or ANTHROPIC_API_KEY "
                "(paid API) in the environment.",
                file=sys.stderr,
            )
            return 1
        results = asyncio.run(
            _run_scenarios_api(
                scenarios,
                mcp_config=args.mcp_config,
                cwd=args.cwd,
                raw_output_dir=raw_dir,
                model=args.model,
            )
        )
    else:
        if args.mcp_config is not None:
            print("  Pre-warming MCP servers (dummy `claude -p ping`)...", file=sys.stderr)
            warm_ms = prewarm_mcp(args.mcp_config, args.cwd)
            print(f"  Pre-warm done in {warm_ms}ms.", file=sys.stderr)

        results = []
        for i, scenario in enumerate(scenarios, 1):
            r = run_scenario(
                scenario, mcp_config=args.mcp_config, cwd=args.cwd, raw_output_dir=raw_dir
            )
            results.append(r)
            _print_progress(i, len(scenarios), scenario["id"], r)

    summary = build_summary(
        results, ref_label=args.ref_label, cwd=args.cwd, mcp_config=args.mcp_config,
    )
    summary["backend"] = args.backend
    if args.backend == "api":
        summary["model"] = args.model
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
