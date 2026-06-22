"""Render the A/B comparison as a Markdown report.

Imported by compare.py; can also be run standalone:

    python3 scripts/eval-descriptions/report.py /tmp/eval-compare.json \\
            /tmp/eval-baseline.json /tmp/eval-head.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _delta(x: float) -> str:
    pts = x * 100
    sign = "+" if pts >= 0 else ""
    arrow = "↑" if pts > 0 else ("↓" if pts < 0 else "·")
    return f"{sign}{pts:.1f}pt {arrow}"


def render_markdown(comparison: dict[str, Any], baseline: dict[str, Any], head: dict[str, Any]) -> str:
    """Render an A/B comparison dict as a Markdown report string."""
    base_label = comparison.get("baseline_label", "baseline")
    head_label = comparison.get("head_label", "head")
    base_sha = comparison.get("baseline_sha", "?")
    head_sha = comparison.get("head_sha", "?")

    by_cat_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_cat_head: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in baseline["results"]:
        by_cat_base[r["category"]].append(r)
    for r in head["results"]:
        by_cat_head[r["category"]].append(r)

    lines: list[str] = []
    lines.append("# Tool-Description Eval: tool-selection accuracy A/B\n")
    lines.append(
        f"**Baseline:** `{base_label}` (`{base_sha}`) — "
        f"**HEAD:** `{head_label}` (`{head_sha}`)  \n"
    )
    lines.append(
        f"**Scenarios:** {comparison['total_scenarios']}  \n"
        f"**Methodology:** Each scenario runs through `claude -p` (Claude CLI "
        f"OAuth) with `--strict-mcp-config`, against the live tapps-mcp MCP "
        f"catalog. We capture the first MCP `tool_use` event and score against "
        f"the expected tool (exact) or any acceptable alternative.\n"
    )
    lines.append("## Headline (raw)\n")
    lines.append("| Metric | Baseline | HEAD | Delta |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| Strict accuracy (exact match) | {_pct(comparison['baseline_strict'])} | "
        f"{_pct(comparison['head_strict'])} | {_delta(comparison['accuracy_delta_strict'])} |"
    )
    lines.append(
        f"| Lenient accuracy (exact + acceptable alternative) | "
        f"{_pct(comparison['baseline_lenient'])} | {_pct(comparison['head_lenient'])} | "
        f"{_delta(comparison['accuracy_delta_lenient'])} |"
    )
    lines.append("")

    # Noise-adjusted view: only count scenarios that ran successfully on
    # BOTH sides (i.e. neither errored). Infrastructure errors — typically
    # MCP cold-start timeouts — should not count as description regressions
    # or improvements; they're orthogonal flakiness. This sub-analysis is
    # the more honest signal when error rates are non-trivial.
    by_b = {r["scenario_id"]: r for r in baseline["results"]}
    by_h = {r["scenario_id"]: r for r in head["results"]}
    common_ok = [
        sid for sid in set(by_b) & set(by_h)
        if by_b[sid]["verdict"] != "error" and by_h[sid]["verdict"] != "error"
    ]
    if common_ok and len(common_ok) < len(by_b):
        PASS = {"exact", "acceptable"}
        b_pass = sum(1 for sid in common_ok if by_b[sid]["verdict"] in PASS)
        h_pass = sum(1 for sid in common_ok if by_h[sid]["verdict"] in PASS)
        n = len(common_ok)
        b_acc = b_pass / n
        h_acc = h_pass / n
        n_errors_b = sum(1 for r in baseline["results"] if r["verdict"] == "error")
        n_errors_h = sum(1 for r in head["results"] if r["verdict"] == "error")
        lines.append("## Headline (noise-adjusted)\n")
        lines.append(
            f"_Excludes {n_errors_b} baseline errors + {n_errors_h} HEAD errors_ "
            f"_(typically MCP cold-start timeouts, not description regressions). "
            f"Scenarios that ran successfully on both sides: {n}._\n"
        )
        lines.append("| Metric | Baseline | HEAD | Delta |")
        lines.append("|---|---:|---:|---:|")
        lines.append(
            f"| Pass rate on common-OK scenarios | {_pct(b_acc)} | {_pct(h_acc)} | "
            f"{_delta(h_acc - b_acc)} |"
        )
        lines.append("")

    # Per-category accuracy
    lines.append("## Per-category accuracy\n")
    lines.append("| Category | n | Baseline strict | HEAD strict | Δ |")
    lines.append("|---|---:|---:|---:|---:|")
    all_cats = sorted(set(by_cat_base) | set(by_cat_head))
    for cat in all_cats:
        b = by_cat_base.get(cat, [])
        h = by_cat_head.get(cat, [])
        n = len(h) if h else len(b)
        if not n:
            continue
        b_strict = sum(1 for r in b if r["verdict"] == "exact") / max(len(b), 1)
        h_strict = sum(1 for r in h if r["verdict"] == "exact") / max(len(h), 1)
        lines.append(
            f"| {cat} | {n} | {_pct(b_strict)} | {_pct(h_strict)} | "
            f"{_delta(h_strict - b_strict)} |"
        )
    lines.append("")

    # Regressions — split signal vs noise
    true_regressions = [
        r for r in comparison["regressions"]
        if r["baseline_verdict"] != "error" and r["head_verdict"] != "error"
    ]
    error_introduced = [
        r for r in comparison["regressions"]
        if r["baseline_verdict"] != "error" and r["head_verdict"] == "error"
    ]
    lines.append(
        f"## True regressions ({len(true_regressions)}) — signal\n"
    )
    lines.append(
        "_Baseline picked correctly, HEAD picked wrong (excluding scenarios "
        "that errored on either side)._\n"
    )
    if not true_regressions:
        lines.append("_None._\n")
    else:
        lines.append("| Scenario | Expected | Baseline picked | HEAD picked |")
        lines.append("|---|---|---|---|")
        for r in true_regressions:
            lines.append(
                f"| `{r['scenario_id']}` | `{r['expected']}` | "
                f"`{r['baseline_tool'] or '—'}` ({r['baseline_verdict']}) | "
                f"`{r['head_tool'] or '—'}` ({r['head_verdict']}) |"
            )
        lines.append("")
    if error_introduced:
        lines.append(
            f"## Error-introduced ({len(error_introduced)}) — likely infra noise\n"
        )
        lines.append(
            "_Baseline ran successfully; HEAD timed out. Likely MCP cold-start "
            "flake; rerun before treating as a real regression._\n"
        )
        lines.append("| Scenario | Expected | Baseline (ran OK) |")
        lines.append("|---|---|---|")
        for r in error_introduced:
            lines.append(
                f"| `{r['scenario_id']}` | `{r['expected']}` | "
                f"`{r['baseline_tool']}` ({r['baseline_verdict']}) |"
            )
        lines.append("")

    # Improvements — split signal vs noise
    true_improvements = [
        r for r in comparison["improvements"]
        if r["baseline_verdict"] != "error" and r["head_verdict"] != "error"
    ]
    error_recovered = [
        r for r in comparison["improvements"]
        if r["baseline_verdict"] == "error" and r["head_verdict"] != "error"
    ]
    lines.append(
        f"## True improvements ({len(true_improvements)}) — signal\n"
    )
    lines.append(
        "_Baseline picked wrong, HEAD picked correctly (excluding scenarios "
        "that errored on either side)._\n"
    )
    if not true_improvements:
        lines.append("_None._\n")
    else:
        lines.append("| Scenario | Expected | Baseline picked | HEAD picked |")
        lines.append("|---|---|---|---|")
        for r in true_improvements:
            lines.append(
                f"| `{r['scenario_id']}` | `{r['expected']}` | "
                f"`{r['baseline_tool'] or '—'}` ({r['baseline_verdict']}) | "
                f"`{r['head_tool'] or '—'}` ({r['head_verdict']}) |"
            )
        lines.append("")
    if error_recovered:
        lines.append(
            f"## Error-recovered ({len(error_recovered)}) — likely infra noise\n"
        )
        lines.append(
            "_Baseline timed out; HEAD ran. Likely the same MCP cold-start "
            "flake that hit the OTHER baseline scenarios._\n"
        )
        lines.append("| Scenario | Expected | HEAD (ran OK) |")
        lines.append("|---|---|---|")
        for r in error_recovered:
            lines.append(
                f"| `{r['scenario_id']}` | `{r['expected']}` | "
                f"`{r['head_tool']}` ({r['head_verdict']}) |"
            )
        lines.append("")

    # Stable wrong (the persistent failures — these are next-iteration targets)
    if comparison["stable_wrong"]:
        lines.append(f"## Stable failures ({len(comparison['stable_wrong'])})\n")
        lines.append(
            "_Scenarios that failed under BOTH baseline and HEAD — the "
            "description rewrite did not fix these. These are the highest-leverage "
            "targets for the next pass._\n"
        )
        head_by_id = {r["scenario_id"]: r for r in head["results"]}
        lines.append("| Scenario | Expected | HEAD picked |")
        lines.append("|---|---|---|")
        for sid in comparison["stable_wrong"]:
            r = head_by_id.get(sid, {})
            lines.append(
                f"| `{sid}` | `{r.get('expected_tool', '?')}` | "
                f"`{r.get('actual_tool') or '—'}` ({r.get('verdict', '?')}) |"
            )
        lines.append("")

    # Methodology / reproduce
    lines.append("## Reproduce\n")
    lines.append("```bash")
    lines.append(f"python3 scripts/eval-descriptions/compare.py {base_label.replace('-parent', '^')} {head_label}")
    lines.append("```")
    lines.append("")
    lines.append(
        "Raw stream-json transcripts per scenario are at "
        "`/tmp/eval-<ref>-raw/<scenario_id>.jsonl` and can be re-scored offline.\n"
    )

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: report.py <compare.json> <baseline.json> <head.json>", file=sys.stderr)
        sys.exit(2)
    compare_p, base_p, head_p = (Path(p) for p in sys.argv[1:4])
    comparison = json.loads(compare_p.read_text(encoding="utf-8"))
    baseline = json.loads(base_p.read_text(encoding="utf-8"))
    head = json.loads(head_p.read_text(encoding="utf-8"))
    sys.stdout.write(render_markdown(comparison, baseline, head))
