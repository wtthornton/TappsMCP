"""Report generation - JSON / Markdown / HTML quality reports.

Combines scoring results, gate results, and expert data into a
unified report.  HTML output uses a simple inline template (no Jinja2
dependency required).
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

import structlog

from tapps_mcp.gates.models import GateResult  # noqa: TC001
from tapps_mcp.scoring.models import ScoreResult  # noqa: TC001

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Score color thresholds
# ---------------------------------------------------------------------------

_SCORE_GOOD_THRESHOLD = 80
_SCORE_WARN_THRESHOLD = 60

# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def generate_report(
    score_results: list[ScoreResult],
    gate_results: list[GateResult] | None = None,
    *,
    report_format: str = "json",
    title: str = "TappsMCP Quality Report",
) -> dict[str, Any]:
    """Generate a quality report from scoring + gate data.

    Args:
        score_results: One or more file scoring results.
        gate_results: Optional gate results aligned 1:1 with *score_results*.
        report_format: ``"json"`` (default), ``"markdown"``, or ``"html"``.
        title: Report title.

    Returns:
        A dict with keys ``format``, ``content``, and ``summary``.
    """
    summary = _build_summary(score_results, gate_results)

    content: str | dict[str, Any]
    if report_format == "markdown":
        content = _render_markdown(title, score_results, gate_results, summary)
    elif report_format == "html":
        content = _render_html(title, score_results, gate_results, summary)
    else:
        content = _render_json(title, score_results, gate_results, summary)

    return {
        "format": report_format,
        "content": content,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------


def _build_summary(
    scores: list[ScoreResult],
    gates: list[GateResult] | None,
) -> dict[str, Any]:
    if not scores:
        return {"files_scored": 0}

    overall_scores = [s.overall_score for s in scores]
    avg = sum(overall_scores) / len(overall_scores)
    gate_passed = 0
    gate_total = 0
    if gates:
        gate_total = len(gates)
        gate_passed = sum(1 for g in gates if g.passed)

    total_lint = sum(len(s.lint_issues) for s in scores)
    total_type = sum(len(s.type_issues) for s in scores)
    total_security = sum(len(s.security_issues) for s in scores)

    return {
        "files_scored": len(scores),
        "avg_score": round(avg, 2),
        "min_score": round(min(overall_scores), 2),
        "max_score": round(max(overall_scores), 2),
        "gate_pass_rate": round(gate_passed / gate_total, 2) if gate_total else None,
        "total_lint_issues": total_lint,
        "total_type_issues": total_type,
        "total_security_issues": total_security,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),  # noqa: UP017
    }


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------


def _render_json(
    title: str,
    scores: list[ScoreResult],
    gates: list[GateResult] | None,
    summary: dict[str, Any],
) -> dict[str, Any]:
    files = []
    for i, s in enumerate(scores):
        entry: dict[str, Any] = {
            "file_path": s.file_path,
            "overall_score": round(s.overall_score, 2),
            "categories": {k: round(v.score, 2) for k, v in s.categories.items()},
            "lint_issues": len(s.lint_issues),
            "type_issues": len(s.type_issues),
            "security_issues": len(s.security_issues),
        }
        if gates and i < len(gates):
            entry["gate_passed"] = gates[i].passed
        files.append(entry)

    return {"title": title, "summary": summary, "files": files}


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def _render_markdown(
    title: str,
    scores: list[ScoreResult],
    gates: list[GateResult] | None,
    summary: dict[str, Any],
) -> str:
    lines: list[str] = [f"# {title}", ""]

    # Summary
    lines.append("## Summary")
    lines.append(f"- **Files scored:** {summary['files_scored']}")
    lines.append(f"- **Avg score:** {summary['avg_score']}")
    lines.append(f"- **Min / Max:** {summary['min_score']} / {summary['max_score']}")
    if summary.get("gate_pass_rate") is not None:
        lines.append(f"- **Gate pass rate:** {summary['gate_pass_rate']:.0%}")
    lines.append(f"- **Lint issues:** {summary['total_lint_issues']}")
    lines.append(f"- **Type issues:** {summary['total_type_issues']}")
    lines.append(f"- **Security issues:** {summary['total_security_issues']}")
    lines.append("")

    # Per-file table
    lines.append("## Files")
    lines.append("| File | Score | Gate | Lint | Type | Security |")
    lines.append("|------|------:|:----:|-----:|-----:|---------:|")
    for i, s in enumerate(scores):
        gate_str = ""
        if gates and i < len(gates):
            gate_str = "PASS" if gates[i].passed else "FAIL"
        lines.append(
            f"| {s.file_path} | {s.overall_score:.1f} | {gate_str} "
            f"| {len(s.lint_issues)} | {len(s.type_issues)} | {len(s.security_issues)} |"
        )
    lines.append("")
    lines.append(f"*Generated {summary.get('generated_at', '')}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML renderer (inline template - no Jinja2 required)
# ---------------------------------------------------------------------------


def _render_html(
    title: str,
    scores: list[ScoreResult],
    gates: list[GateResult] | None,
    summary: dict[str, Any],
) -> str:
    h = html.escape

    rows: list[str] = []
    for i, s in enumerate(scores):
        gate_str = ""
        if gates and i < len(gates):
            gate_str = "PASS" if gates[i].passed else "FAIL"
        color = _score_color(s.overall_score)
        rows.append(
            f"<tr>"
            f"<td>{h(s.file_path)}</td>"
            f'<td style="color:{color};text-align:right">{s.overall_score:.1f}</td>'
            f"<td style='text-align:center'>{gate_str}</td>"
            f"<td style='text-align:right'>{len(s.lint_issues)}</td>"
            f"<td style='text-align:right'>{len(s.type_issues)}</td>"
            f"<td style='text-align:right'>{len(s.security_issues)}</td>"
            f"</tr>"
        )

    gate_rate = summary.get("gate_pass_rate")
    gate_line = f"<p>Gate pass rate: {gate_rate:.0%}</p>" if gate_rate is not None else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{h(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: .3rem; }}
.card {{ display: inline-block; background: #f5f5f5; border-radius: 8px;
  padding: 1rem 1.5rem; margin: .5rem; }}
.card .value {{ font-size: 1.8rem; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; }}
th {{ background: #f0f0f0; }}
</style>
</head>
<body>
<h1>{h(title)}</h1>
<div>
  <div class="card"><div class="value">{summary['files_scored']}</div>Files</div>
  <div class="card"><div class="value">{summary['avg_score']}</div>Avg Score</div>
  <div class="card"><div class="value">{summary['total_lint_issues']}</div>Lint</div>
  <div class="card"><div class="value">{summary['total_security_issues']}</div>Security</div>
</div>
{gate_line}
<table>
<tr><th>File</th><th>Score</th><th>Gate</th><th>Lint</th><th>Type</th><th>Security</th></tr>
{''.join(rows)}
</table>
<p><small>Generated {h(str(summary.get('generated_at', '')))}</small></p>
</body></html>"""


def _score_color(score: float) -> str:
    if score >= _SCORE_GOOD_THRESHOLD:
        return "#2e7d32"
    if score >= _SCORE_WARN_THRESHOLD:
        return "#f57f17"
    return "#c62828"
