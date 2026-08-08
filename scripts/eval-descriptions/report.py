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

#: Verdicts that count as a pass under lenient scoring. Mirrors run.py.
_LENIENT_PASS: frozenset[str] = frozenset(("exact", "acceptable"))


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _delta(x: float) -> str:
    pts = x * 100
    sign = "+" if pts >= 0 else ""
    arrow = "↑" if pts > 0 else ("↓" if pts < 0 else "·")
    return f"{sign}{pts:.1f}pt {arrow}"


def _count_errors(results: list[dict[str, Any]]) -> int:
    """How many scenarios errored out (infrastructure noise, not a wrong pick)."""
    return sum(1 for r in results if r["verdict"] == "error")


def _pass_rate(by_id: dict[str, dict[str, Any]], sids: list[str]) -> float:
    """Lenient pass rate over `sids`. Caller guarantees `sids` is non-empty."""
    return sum(1 for sid in sids if by_id[sid]["verdict"] in _LENIENT_PASS) / len(sids)


def _strict_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of `results` where the exact expected tool was picked."""
    return sum(1 for r in results if r["verdict"] == "exact") / max(len(results), 1)


def _group_by_category(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket scenario results by their ``category`` field."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        grouped[r["category"]].append(r)
    return grouped


def _both_sides_table(rows: list[dict[str, Any]]) -> list[str]:
    """Four-column table: what each ref picked for a scenario."""
    return [
        "| Scenario | Expected | Baseline picked | HEAD picked |",
        "|---|---|---|---|",
        *(
            f"| `{r['scenario_id']}` | `{r['expected']}` | "
            f"`{r['baseline_tool'] or '—'}` ({r['baseline_verdict']}) | "
            f"`{r['head_tool'] or '—'}` ({r['head_verdict']}) |"
            for r in rows
        ),
        "",
    ]


def _one_side_table(rows: list[dict[str, Any]], *, side: str, col_label: str) -> list[str]:
    """Three-column table for noise buckets, showing only the ref that ran OK.

    ``side`` selects which half of the row to read — ``"baseline"`` or ``"head"``.
    """
    return [
        f"| Scenario | Expected | {col_label} |",
        "|---|---|---|",
        *(
            f"| `{r['scenario_id']}` | `{r['expected']}` | "
            f"`{r[f'{side}_tool']}` ({r[f'{side}_verdict']}) |"
            for r in rows
        ),
        "",
    ]


def _render_header(comparison: dict[str, Any]) -> list[str]:
    """Title, ref identities, and methodology preamble."""
    base_label = comparison.get("baseline_label", "baseline")
    head_label = comparison.get("head_label", "head")
    base_sha = comparison.get("baseline_sha", "?")
    head_sha = comparison.get("head_sha", "?")
    return [
        "# Tool-Description Eval: tool-selection accuracy A/B\n",
        f"**Baseline:** `{base_label}` (`{base_sha}`) — "
        f"**HEAD:** `{head_label}` (`{head_sha}`)  \n",
        f"**Scenarios:** {comparison['total_scenarios']}  \n"
        f"**Methodology:** Each scenario runs through `claude -p` (Claude CLI "
        f"OAuth) with `--strict-mcp-config`, against the live tapps-mcp MCP "
        f"catalog. We capture the first MCP `tool_use` event and score against "
        f"the expected tool (exact) or any acceptable alternative.\n",
    ]


def _render_headline_raw(comparison: dict[str, Any]) -> list[str]:
    """Strict and lenient accuracy over every scenario, errors included."""
    return [
        "## Headline (raw)\n",
        "| Metric | Baseline | HEAD | Delta |",
        "|---|---:|---:|---:|",
        f"| Strict accuracy (exact match) | {_pct(comparison['baseline_strict'])} | "
        f"{_pct(comparison['head_strict'])} | {_delta(comparison['accuracy_delta_strict'])} |",
        f"| Lenient accuracy (exact + acceptable alternative) | "
        f"{_pct(comparison['baseline_lenient'])} | {_pct(comparison['head_lenient'])} | "
        f"{_delta(comparison['accuracy_delta_lenient'])} |",
        "",
    ]


def _render_headline_noise_adjusted(
    baseline: dict[str, Any], head: dict[str, Any]
) -> list[str]:
    """Pass rate over scenarios that ran successfully on BOTH sides.

    Infrastructure errors — typically MCP cold-start timeouts — should not
    count as description regressions or improvements; they're orthogonal
    flakiness. This sub-analysis is the more honest signal when error rates
    are non-trivial. Returns no lines when nothing errored.
    """
    by_b = {r["scenario_id"]: r for r in baseline["results"]}
    by_h = {r["scenario_id"]: r for r in head["results"]}
    common_ok = [
        sid for sid in set(by_b) & set(by_h)
        if by_b[sid]["verdict"] != "error" and by_h[sid]["verdict"] != "error"
    ]
    if not common_ok or len(common_ok) >= len(by_b):
        return []

    n = len(common_ok)
    b_acc = _pass_rate(by_b, common_ok)
    h_acc = _pass_rate(by_h, common_ok)
    n_errors_b = _count_errors(baseline["results"])
    n_errors_h = _count_errors(head["results"])
    return [
        "## Headline (noise-adjusted)\n",
        f"_Excludes {n_errors_b} baseline errors + {n_errors_h} HEAD errors_ "
        f"_(typically MCP cold-start timeouts, not description regressions). "
        f"Scenarios that ran successfully on both sides: {n}._\n",
        "| Metric | Baseline | HEAD | Delta |",
        "|---|---:|---:|---:|",
        f"| Pass rate on common-OK scenarios | {_pct(b_acc)} | {_pct(h_acc)} | "
        f"{_delta(h_acc - b_acc)} |",
        "",
    ]


def _render_per_category(baseline: dict[str, Any], head: dict[str, Any]) -> list[str]:
    """Strict accuracy broken out by scenario category."""
    by_cat_base = _group_by_category(baseline["results"])
    by_cat_head = _group_by_category(head["results"])

    lines = [
        "## Per-category accuracy\n",
        "| Category | n | Baseline strict | HEAD strict | Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    for cat in sorted(set(by_cat_base) | set(by_cat_head)):
        b = by_cat_base.get(cat, [])
        h = by_cat_head.get(cat, [])
        n = len(h) if h else len(b)
        if not n:
            continue
        b_strict = _strict_rate(b)
        h_strict = _strict_rate(h)
        lines.append(
            f"| {cat} | {n} | {_pct(b_strict)} | {_pct(h_strict)} | "
            f"{_delta(h_strict - b_strict)} |"
        )
    lines.append("")
    return lines


def _render_regressions(comparison: dict[str, Any]) -> list[str]:
    """True regressions (signal), then the error-introduced noise bucket."""
    rows = comparison["regressions"]
    true_regressions = [
        r for r in rows
        if r["baseline_verdict"] != "error" and r["head_verdict"] != "error"
    ]
    error_introduced = [
        r for r in rows
        if r["baseline_verdict"] != "error" and r["head_verdict"] == "error"
    ]

    lines = [
        f"## True regressions ({len(true_regressions)}) — signal\n",
        "_Baseline picked correctly, HEAD picked wrong (excluding scenarios "
        "that errored on either side)._\n",
    ]
    if true_regressions:
        lines.extend(_both_sides_table(true_regressions))
    else:
        lines.append("_None._\n")

    if error_introduced:
        lines.append(
            f"## Error-introduced ({len(error_introduced)}) — likely infra noise\n"
        )
        lines.append(
            "_Baseline ran successfully; HEAD timed out. Likely MCP cold-start "
            "flake; rerun before treating as a real regression._\n"
        )
        lines.extend(
            _one_side_table(error_introduced, side="baseline", col_label="Baseline (ran OK)")
        )
    return lines


def _render_improvements(comparison: dict[str, Any]) -> list[str]:
    """True improvements (signal), then the error-recovered noise bucket."""
    rows = comparison["improvements"]
    true_improvements = [
        r for r in rows
        if r["baseline_verdict"] != "error" and r["head_verdict"] != "error"
    ]
    error_recovered = [
        r for r in rows
        if r["baseline_verdict"] == "error" and r["head_verdict"] != "error"
    ]

    lines = [
        f"## True improvements ({len(true_improvements)}) — signal\n",
        "_Baseline picked wrong, HEAD picked correctly (excluding scenarios "
        "that errored on either side)._\n",
    ]
    if true_improvements:
        lines.extend(_both_sides_table(true_improvements))
    else:
        lines.append("_None._\n")

    if error_recovered:
        lines.append(
            f"## Error-recovered ({len(error_recovered)}) — likely infra noise\n"
        )
        lines.append(
            "_Baseline timed out; HEAD ran. Likely the same MCP cold-start "
            "flake that hit the OTHER baseline scenarios._\n"
        )
        lines.extend(
            _one_side_table(error_recovered, side="head", col_label="HEAD (ran OK)")
        )
    return lines


def _stable_failure_row(sid: str, head_by_id: dict[str, dict[str, Any]]) -> str:
    r = head_by_id.get(sid, {})
    return (
        f"| `{sid}` | `{r.get('expected_tool', '?')}` | "
        f"`{r.get('actual_tool') or '—'}` ({r.get('verdict', '?')}) |"
    )


def _render_stable_failures(comparison: dict[str, Any], head: dict[str, Any]) -> list[str]:
    """Scenarios that failed under BOTH refs — the next-iteration targets."""
    stable_wrong = comparison["stable_wrong"]
    if not stable_wrong:
        return []
    head_by_id = {r["scenario_id"]: r for r in head["results"]}
    return [
        f"## Stable failures ({len(stable_wrong)})\n",
        "_Scenarios that failed under BOTH baseline and HEAD — the "
        "description rewrite did not fix these. These are the highest-leverage "
        "targets for the next pass._\n",
        "| Scenario | Expected | HEAD picked |",
        "|---|---|---|",
        *(_stable_failure_row(sid, head_by_id) for sid in stable_wrong),
        "",
    ]


def _render_reproduce(comparison: dict[str, Any]) -> list[str]:
    """The command that regenerates this report, plus where raw output lives."""
    base_label = comparison.get("baseline_label", "baseline")
    head_label = comparison.get("head_label", "head")
    cmd = (
        f"python3 scripts/eval-descriptions/compare.py "
        f"{base_label.replace('-parent', '^')} {head_label}"
    )
    return [
        "## Reproduce\n",
        "```bash",
        cmd,
        "```",
        "",
        "Raw stream-json transcripts per scenario are at "
        "`/tmp/eval-<ref>-raw/<scenario_id>.jsonl` and can be re-scored offline.\n",
    ]


def render_markdown(comparison: dict[str, Any], baseline: dict[str, Any], head: dict[str, Any]) -> str:
    """Render an A/B comparison dict as a Markdown report string."""
    sections = (
        _render_header(comparison),
        _render_headline_raw(comparison),
        _render_headline_noise_adjusted(baseline, head),
        _render_per_category(baseline, head),
        _render_regressions(comparison),
        _render_improvements(comparison),
        _render_stable_failures(comparison, head),
        _render_reproduce(comparison),
    )
    return "\n".join(line for section in sections for line in section)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: report.py <compare.json> <baseline.json> <head.json>", file=sys.stderr)
        sys.exit(2)
    compare_p, base_p, head_p = (Path(p) for p in sys.argv[1:4])
    comparison = json.loads(compare_p.read_text(encoding="utf-8"))
    baseline = json.loads(base_p.read_text(encoding="utf-8"))
    head = json.loads(head_p.read_text(encoding="utf-8"))
    sys.stdout.write(render_markdown(comparison, baseline, head))
