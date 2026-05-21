#!/usr/bin/env python3
"""A/B compare tool-selection accuracy between two git refs.

For each ref, materializes the repo via `git worktree`, runs scenarios.yaml
through `run.py` against that ref's MCP descriptions, and diffs the
per-scenario verdicts.

Usage:
    # Compare cc1d340^ (baseline, pre-rewrite) vs HEAD (post-rewrite)
    python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD

    # Compare two arbitrary refs
    python3 scripts/eval-descriptions/compare.py v3.10.10 v3.10.16

    # Skip the actual eval, just regenerate the report from existing JSON
    python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD --skip-run

Outputs:
    /tmp/eval-<ref>.json for each ref
    /tmp/eval-compare.json with the diff
    docs/benchmarks/<date>-description-eval.md (markdown report)
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 — we invoke `git`/`uv`/`python3` with hard-coded arg lists.
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_SCRIPT = Path(__file__).resolve().parent / "run.py"


def safe_ref_label(ref: str) -> str:
    """Sanitize a git ref for use in a file name."""
    return ref.replace("/", "-").replace("^", "-parent").replace("~", "-tilde")


def short_sha(ref: str) -> str:
    """Resolve `ref` to a 7-char SHA."""
    return subprocess.run(
        ["git", "rev-parse", "--short", ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def add_worktree(ref: str, target: Path) -> None:
    """Create a git worktree at `target` checked out to `ref`."""
    if target.exists():
        subprocess.run(  # nosec B603 — explicit args, no shell, no user input.
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
    subprocess.run(  # nosec B603 — explicit args, no shell, no user input.
        ["git", "worktree", "add", "--detach", str(target), ref],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


def remove_worktree(target: Path) -> None:
    subprocess.run(  # nosec B603 — explicit args, no shell, no user input.
        ["git", "worktree", "remove", "--force", str(target)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )


def sync_uv_in_worktree(worktree: Path) -> None:
    """Run `uv sync --all-packages` so the worktree has a venv that resolves
    the worktree's source — `uv run tapps-mcp serve` in the worktree will
    then pick up the worktree's descriptions, not the main checkout's."""
    print(f"  uv sync --all-packages in {worktree}...", file=sys.stderr)
    subprocess.run(  # nosec B603 — explicit args, no shell, no user input.
        ["uv", "sync", "--all-packages"],
        cwd=worktree,
        check=True,
        capture_output=True,
    )


def copy_mcp_config(worktree: Path) -> Path:
    """Copy the main .mcp.json (gitignored) into the worktree so the eval
    agent has a tool catalog. We rewrite TAPPS_MCP_PROJECT_ROOT to point at
    the worktree, and command/args to use that worktree's uv run."""
    src = REPO_ROOT / ".mcp.json"
    if not src.exists():
        raise FileNotFoundError(
            f"{src} not found. Run `tapps_init` or copy from another checkout."
        )
    raw = src.read_text(encoding="utf-8")
    data = json.loads(raw)
    # Re-target every server entry's command/args to the worktree's uv run
    # so MCP servers spawn against the worktree's source tree, not the main one.
    for entry in (data.get("mcpServers") or {}).values():
        if isinstance(entry, dict):
            args = entry.get("args")
            if isinstance(args, list) and entry.get("command") == "uv":
                # Insert `--directory <worktree>` after `run` so uv runs the
                # worktree's environment.
                new_args: list[str] = []
                for a in args:
                    new_args.append(a)
                    if a == "run":
                        new_args.extend(["--directory", str(worktree)])
                entry["args"] = new_args
            env = entry.get("env")
            if isinstance(env, dict) and "TAPPS_MCP_PROJECT_ROOT" in env:
                env["TAPPS_MCP_PROJECT_ROOT"] = str(worktree)
            if isinstance(env, dict) and "DOCS_MCP_PROJECT_ROOT" in env:
                env["DOCS_MCP_PROJECT_ROOT"] = str(worktree)
    out = worktree / ".mcp.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out


def run_eval(
    ref: str,
    *,
    worktree: Path,
    output_json: Path,
    only: str = "",
    backend: str = "cli",
    model: str | None = None,
) -> dict:
    mcp_config = copy_mcp_config(worktree)
    cmd: list[str] = [
        sys.executable,
        str(RUN_SCRIPT),
        "--cwd", str(worktree),
        "--mcp-config", str(mcp_config),
        "--output", str(output_json),
        "--ref-label", ref,
        "--backend", backend,
    ]
    if model:
        cmd.extend(["--model", model])
    if only:
        cmd.extend(["--only", only])
    print(f"  Running eval against {ref} (backend={backend})...", file=sys.stderr)
    subprocess.run(cmd, check=True)  # nosec B603 — explicit args, no shell, no user input.
    return json.loads(output_json.read_text(encoding="utf-8"))


def diff_results(baseline: dict, head: dict) -> dict:
    """Per-scenario verdict diff. Returns:
        {
          regressions: [scenario_id, baseline_verdict, head_verdict],
          improvements: [...],
          stable_correct: [...],
          stable_wrong: [...],
          accuracy_delta_strict: float,
          accuracy_delta_lenient: float,
        }
    """
    by_id_base = {r["scenario_id"]: r for r in baseline["results"]}
    by_id_head = {r["scenario_id"]: r for r in head["results"]}
    all_ids = set(by_id_base) | set(by_id_head)

    regressions: list[dict] = []
    improvements: list[dict] = []
    stable_correct: list[str] = []
    stable_wrong: list[str] = []

    PASS = {"exact", "acceptable"}
    for sid in sorted(all_ids):
        b = by_id_base.get(sid)
        h = by_id_head.get(sid)
        if b is None or h is None:
            continue
        b_pass = b["verdict"] in PASS
        h_pass = h["verdict"] in PASS
        if b_pass and not h_pass:
            regressions.append({
                "scenario_id": sid,
                "baseline_verdict": b["verdict"],
                "baseline_tool": b["actual_tool"],
                "head_verdict": h["verdict"],
                "head_tool": h["actual_tool"],
                "expected": h["expected_tool"],
            })
        elif h_pass and not b_pass:
            improvements.append({
                "scenario_id": sid,
                "baseline_verdict": b["verdict"],
                "baseline_tool": b["actual_tool"],
                "head_verdict": h["verdict"],
                "head_tool": h["actual_tool"],
                "expected": h["expected_tool"],
            })
        elif b_pass and h_pass:
            stable_correct.append(sid)
        else:
            stable_wrong.append(sid)

    return {
        "baseline_label": baseline.get("ref_label", "baseline"),
        "head_label": head.get("ref_label", "head"),
        "baseline_strict": baseline["accuracy_strict"],
        "baseline_lenient": baseline["accuracy_lenient"],
        "head_strict": head["accuracy_strict"],
        "head_lenient": head["accuracy_lenient"],
        "accuracy_delta_strict": head["accuracy_strict"] - baseline["accuracy_strict"],
        "accuracy_delta_lenient": head["accuracy_lenient"] - baseline["accuracy_lenient"],
        "regressions": regressions,
        "improvements": improvements,
        "stable_correct": stable_correct,
        "stable_wrong": stable_wrong,
        "total_scenarios": len(all_ids),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_ref", help="Git ref for the baseline (e.g. cc1d340^)")
    parser.add_argument("head_ref", help="Git ref for the new descriptions (e.g. HEAD)")
    parser.add_argument(
        "--skip-run", action="store_true",
        help="Skip the actual eval; just rebuild report from existing JSON.",
    )
    parser.add_argument(
        "--only", type=str, default="",
        help="Comma-separated scenario ids to run (default: all).",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(tempfile.gettempdir()) / "eval-compare.json",
        help="Where to write the comparison JSON.",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help=(
            "Where to write the markdown report (default: "
            "docs/benchmarks/<date>-description-eval.md)."
        ),
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="cli",
        choices=("cli", "api"),
        help=(
            "Eval backend forwarded to run.py. cli (default): Max-plan "
            "OAuth via Claude CLI. api: Anthropic Messages API direct "
            "(needs ANTHROPIC_API_KEY); use for CI to sidestep rate limits."
        ),
    )
    parser.add_argument(
        "--model", type=str, default="",
        help="Model override for --backend=api (default: run.py's default).",
    )
    return parser


def _run_both_evals(
    *,
    baseline_ref: str,
    head_ref: str,
    base_sha: str,
    head_sha: str,
    base_json: Path,
    head_json: Path,
    only: str,
    backend: str = "cli",
    model: str = "",
) -> None:
    """Materialize both worktrees, sync, eval each, clean up."""
    model_arg = model or None
    with tempfile.TemporaryDirectory(prefix="eval-wt-") as tmpdir:
        tmp = Path(tmpdir)
        base_wt = tmp / "baseline"
        head_wt = tmp / "head"
        try:
            print(
                f"==> Setting up baseline worktree at {base_wt} "
                f"({baseline_ref}={base_sha})", file=sys.stderr,
            )
            add_worktree(baseline_ref, base_wt)
            sync_uv_in_worktree(base_wt)
            run_eval(
                baseline_ref,
                worktree=base_wt,
                output_json=base_json,
                only=only,
                backend=backend,
                model=model_arg,
            )
            print(
                f"==> Setting up head worktree at {head_wt} "
                f"({head_ref}={head_sha})", file=sys.stderr,
            )
            add_worktree(head_ref, head_wt)
            sync_uv_in_worktree(head_wt)
            run_eval(
                head_ref,
                worktree=head_wt,
                output_json=head_json,
                only=only,
                backend=backend,
                model=model_arg,
            )
        finally:
            remove_worktree(base_wt)
            remove_worktree(head_wt)


def _write_report(
    *,
    comparison: dict,
    baseline: dict,
    head: dict,
    report_path: Path | None,
) -> Path:
    # Sibling-module import; sys.path is adjusted in __main__ block below.
    from report import render_markdown  # type: ignore[import-not-found]
    out = report_path or (
        REPO_ROOT / "docs" / "benchmarks" / f"{date.today():%Y-%m-%d}-description-eval.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(comparison, baseline, head), encoding="utf-8")
    return out


def main() -> int:
    args = _build_arg_parser().parse_args()
    base_label = safe_ref_label(args.baseline_ref)
    head_label = safe_ref_label(args.head_ref)
    base_sha = short_sha(args.baseline_ref)
    head_sha = short_sha(args.head_ref)
    tmp_root = Path(tempfile.gettempdir())
    base_json = tmp_root / f"eval-{base_label}.json"
    head_json = tmp_root / f"eval-{head_label}.json"

    if not args.skip_run:
        _run_both_evals(
            baseline_ref=args.baseline_ref, head_ref=args.head_ref,
            base_sha=base_sha, head_sha=head_sha,
            base_json=base_json, head_json=head_json, only=args.only,
            backend=args.backend, model=args.model,
        )

    baseline = json.loads(base_json.read_text(encoding="utf-8"))
    head = json.loads(head_json.read_text(encoding="utf-8"))
    comparison = diff_results(baseline, head)
    comparison["baseline_sha"] = base_sha
    comparison["head_sha"] = head_sha

    args.output.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    print(f"\nComparison JSON: {args.output}", file=sys.stderr)

    report_path = _write_report(
        comparison=comparison, baseline=baseline, head=head, report_path=args.report,
    )
    print(f"Report: {report_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # Allow `from report import render_markdown` to find the sibling module.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
