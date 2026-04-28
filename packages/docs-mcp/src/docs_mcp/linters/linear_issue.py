"""Pure logic for linting a single Linear issue against the TappsMCP agent-issue
template (see ``docs/linear/AGENT_ISSUES.md``).

No MCP or I/O dependencies. Takes strings, returns a structured result. The
MCP tool wrapper lives in ``server_linear_tools.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Rule IDs — keep stable; consumers (validator, triage) branch on them.
RULE_AUTOLINK_MANGLED = "autolink-mangled"
RULE_UUID_WRAPPED_REF = "uuid-wrapped-ref"
RULE_TITLE_TOO_LONG = "title-too-long"
RULE_MISSING_FILE_ANCHOR = "missing-file-anchor"
RULE_MISSING_ACCEPTANCE = "missing-acceptance"
RULE_ACCEPTANCE_EMPTY = "acceptance-empty"
RULE_CODE_BLOCK_NO_ANCHOR = "code-block-no-anchor"
RULE_MISSING_ESTIMATE = "missing-estimate"
RULE_MISSING_PRIORITY = "missing-priority"

TITLE_MAX_LEN = 80
CHARS_PER_TOKEN = 4  # Rough approximation consistent across rule engines.

LABEL_SPEC_READY = "spec-ready"

# Status names for the new status-based workflow. ``needs-spec`` and
# ``agent-blocked`` were retired as labels — Triage status now expresses both
# "issue needs spec/review" and "issue is blocked on a human decision".
STATUS_TRIAGE = "Triage"
STATUS_BACKLOG = "Backlog"

_SEVERITY_PENALTY = {SEVERITY_HIGH: 25, SEVERITY_MEDIUM: 10, SEVERITY_LOW: 2}

# Regex: Linear autolinker mangle — `[TEXT](<http(s)://TEXT>)` where TEXT matches.
# The key signature is angle-bracketed URL inside the parens whose inner host
# part equals the display text. Filenames like AGENTS.md hit this pattern.
_AUTOLINK_MANGLE_RE = re.compile(r"\[([^\]]+)\]\(<https?://([^>\s]+)>\)")

# Regex: UUID-wrapped issue ref — `<issue id="...">TAP-###</issue>`.
_UUID_WRAPPED_REF_RE = re.compile(r'<issue\s+id="[^"]+"\s*>\s*(TAP-\d+)\s*</issue>')

# Regex: file anchor — `path/to/file.ext:LINE` or `:LINE-LINE`.
_FILE_ANCHOR_RE = re.compile(
    r"[\w./\\-]+\.(?:py|pyi|ts|tsx|js|jsx|md|yaml|yml|toml|json|rs|go|java|rb|cpp|c|h):\d+(?:-\d+)?"
)

# Regex: fenced code block opening fence (capturing position only).
_FENCE_RE = re.compile(r"^```", re.MULTILINE)

# Markers that suggest human/policy dependency — pushes the issue to Triage.
_BLOCKED_MARKERS_RE = re.compile(
    r"\b(?:blocked by|waiting on|waiting for|needs approval|pending decision|design call)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    """A single rule violation on an issue."""

    rule: str
    severity: str
    message: str
    location: str  # "title" | "description:Lnn" | "metadata"
    fix_hint: str = ""


@dataclass
class LintResult:
    """Structured lint result for one Linear issue.

    ``suggested_label`` is ``"spec-ready"`` for agent-ready issues and the
    empty string otherwise. ``suggested_status`` is the corresponding
    workflow status: ``"Backlog"`` (agent-ready, queued for pickup) or
    ``"Triage"`` (needs spec/review or is blocked on a human decision).
    """

    agent_ready: bool
    score: int
    findings: list[Finding]
    suggested_label: str
    suggested_status: str
    tokens: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_ready": self.agent_ready,
            "score": self.score,
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity,
                    "message": f.message,
                    "location": f.location,
                    "fix_hint": f.fix_hint,
                }
                for f in self.findings
            ],
            "suggested_label": self.suggested_label,
            "suggested_status": self.suggested_status,
            "tokens": self.tokens,
        }


@dataclass
class _Context:
    title: str
    description: str
    labels: list[str]
    priority: int | None
    estimate: float | None
    parent_id: str
    findings: list[Finding] = field(default_factory=list)
    noise_bytes: int = 0

    def add(self, rule: str, severity: str, message: str, location: str, fix_hint: str = "") -> None:
        self.findings.append(
            Finding(rule=rule, severity=severity, message=message, location=location, fix_hint=fix_hint)
        )


def lint_issue(
    title: str,
    description: str = "",
    labels: list[str] | None = None,
    priority: int | None = None,
    estimate: float | None = None,
    parent_id: str = "",
    *,
    is_epic: bool = False,
) -> LintResult:
    """Lint one Linear issue against the TappsMCP agent template.

    Args:
        title: Issue title (required).
        description: Issue description markdown.
        labels: Labels applied to the issue.
        priority: Linear priority (0=None, 1=Urgent, 2=High, 3=Normal, 4=Low).
            ``None`` means not provided; treated as a finding.
        estimate: Story points. ``None`` means not provided; treated as a
            finding for non-epic issues.
        parent_id: Parent issue id (affects hierarchy suggestions elsewhere;
            accepted here for forward compat).
        is_epic: If True, epic-specific rules apply (estimate not required).
    """
    ctx = _Context(
        title=title,
        description=description,
        labels=list(labels) if labels else [],
        priority=priority,
        estimate=estimate,
        parent_id=parent_id,
    )

    _check_title(ctx)
    _check_autolink_mangle(ctx)
    _check_uuid_wrapped_refs(ctx)
    _check_file_anchor(ctx, is_epic=is_epic)
    _check_acceptance(ctx, is_epic=is_epic)
    _check_code_block_anchors(ctx)
    _check_metadata(ctx, is_epic=is_epic)

    score = _score(ctx.findings)
    agent_ready = _is_agent_ready(ctx.findings)
    suggested_label = _suggest_label(ctx)
    suggested_status = _suggest_status(ctx)
    tokens = _estimate_tokens(ctx)

    return LintResult(
        agent_ready=agent_ready,
        score=score,
        findings=ctx.findings,
        suggested_label=suggested_label,
        suggested_status=suggested_status,
        tokens=tokens,
    )


def _check_title(ctx: _Context) -> None:
    if not ctx.title.strip():
        ctx.add(
            rule=RULE_TITLE_TOO_LONG,
            severity=SEVERITY_HIGH,
            message="Title is empty.",
            location="title",
            fix_hint="Use pattern `file.py: symptom` (≤80 chars).",
        )
        return
    if len(ctx.title) > TITLE_MAX_LEN:
        ctx.add(
            rule=RULE_TITLE_TOO_LONG,
            severity=SEVERITY_MEDIUM,
            message=f"Title is {len(ctx.title)} chars (limit {TITLE_MAX_LEN}).",
            location="title",
            fix_hint="Drop em-dash preambles. Keep the symptom; move detail to description.",
        )


def _check_autolink_mangle(ctx: _Context) -> None:
    for match in _AUTOLINK_MANGLE_RE.finditer(ctx.description):
        text, url_host = match.group(1), match.group(2)
        if text.strip() != url_host.strip():
            continue  # Real external link like [name](<http://example.com>) — leave alone.
        ctx.noise_bytes += len(match.group(0)) - len(f"`{text}`")
        ctx.add(
            rule=RULE_AUTOLINK_MANGLED,
            severity=SEVERITY_MEDIUM,
            message=f"Linear autolinker mangled `{text}` into a broken link.",
            location=_locate(ctx.description, match.start()),
            fix_hint=f"Replace `{match.group(0)}` with inline code: `` `{text}` ``.",
        )


def _check_uuid_wrapped_refs(ctx: _Context) -> None:
    for match in _UUID_WRAPPED_REF_RE.finditer(ctx.description):
        ref = match.group(1)
        ctx.noise_bytes += len(match.group(0)) - len(ref)
        ctx.add(
            rule=RULE_UUID_WRAPPED_REF,
            severity=SEVERITY_LOW,
            message=f"`{ref}` is wrapped in an `<issue id=...>` UUID — noise.",
            location=_locate(ctx.description, match.start()),
            fix_hint=f"Replace with bare `{ref}`.",
        )


def _check_file_anchor(ctx: _Context, *, is_epic: bool) -> None:
    if is_epic:
        return  # Epics may legitimately reference many files via description, not one anchor.
    if not _FILE_ANCHOR_RE.search(ctx.description):
        ctx.add(
            rule=RULE_MISSING_FILE_ANCHOR,
            severity=SEVERITY_HIGH,
            message="No `file.ext:LINE` anchor found in description.",
            location="description",
            fix_hint="Add a `## Where` section with `path/to/file.py:LINE-RANGE`.",
        )


def _check_acceptance(ctx: _Context, *, is_epic: bool) -> None:
    # Look for `## Acceptance` heading (case-insensitive, allow trailing words like "Criteria").
    heading_re = re.compile(r"^##\s+Acceptance\b.*$", re.MULTILINE | re.IGNORECASE)
    heading_match = heading_re.search(ctx.description)

    if not heading_match:
        ctx.add(
            rule=RULE_MISSING_ACCEPTANCE,
            severity=SEVERITY_HIGH,
            message="No `## Acceptance` section found.",
            location="description",
            fix_hint="Add `## Acceptance` with ≥1 verifiable checkbox item.",
        )
        return

    # Extract the Acceptance block: from heading to next `## ` heading or EOF.
    start = heading_match.end()
    next_heading = re.search(r"^##\s", ctx.description[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(ctx.description)
    block = ctx.description[start:end]

    checkboxes = re.findall(r"^\s*-\s*\[[ xX]\]\s+\S", block, re.MULTILINE)
    if not checkboxes:
        ctx.add(
            rule=RULE_ACCEPTANCE_EMPTY,
            severity=SEVERITY_HIGH,
            message="`## Acceptance` section has no `- [ ]` checkboxes.",
            location=_locate(ctx.description, heading_match.start()),
            fix_hint="Add verifiable checkbox items (e.g., `- [ ] pytest test_X passes`).",
        )


def _check_code_block_anchors(ctx: _Context) -> None:
    """Flag fenced code blocks not near a `file.py:LINE` anchor.

    Heuristic: for each opening ``` fence, require an anchor within 10 lines
    before or after. Skips blocks labeled ```markdown (templates) and ```python
    inside examples where the surrounding context supplies intent.
    """
    lines = ctx.description.splitlines()
    fence_line_indices: list[int] = []
    in_block = False
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            if not in_block:
                fence_line_indices.append(idx)
            in_block = not in_block

    for open_idx in fence_line_indices:
        window_start = max(0, open_idx - 10)
        window_end = min(len(lines), open_idx + 11)
        window = "\n".join(lines[window_start:window_end])
        if _FILE_ANCHOR_RE.search(window):
            continue
        ctx.add(
            rule=RULE_CODE_BLOCK_NO_ANCHOR,
            severity=SEVERITY_LOW,
            message="Fenced code block has no `file.ext:LINE` anchor nearby.",
            location=f"description:L{open_idx + 1}",
            fix_hint="Add an anchor above the block, or delete the snippet and rely on the anchor.",
        )


def _check_metadata(ctx: _Context, *, is_epic: bool) -> None:
    if ctx.priority is None or ctx.priority == 0:
        ctx.add(
            rule=RULE_MISSING_PRIORITY,
            severity=SEVERITY_LOW,
            message="No priority set (0=None).",
            location="metadata",
            fix_hint="Set priority 1-4 so agents can sort the backlog.",
        )
    if not is_epic and (ctx.estimate is None or ctx.estimate <= 0):
        ctx.add(
            rule=RULE_MISSING_ESTIMATE,
            severity=SEVERITY_LOW,
            message="No estimate set.",
            location="metadata",
            fix_hint="Add a point estimate so agents can budget a session.",
        )


def _score(findings: list[Finding]) -> int:
    score = 100
    for f in findings:
        score -= _SEVERITY_PENALTY.get(f.severity, 0)
    return max(0, score)


def _is_agent_ready(findings: list[Finding]) -> bool:
    """Agent-ready iff no HIGH-severity findings. Mediums/lows are fixable but
    don't block agent pickup."""
    return not any(f.severity == SEVERITY_HIGH for f in findings)


def _suggest_label(ctx: _Context) -> str:
    """Return ``spec-ready`` for agent-ready issues, ``""`` otherwise.

    Agents in workspaces using status-based gating should read
    ``suggested_status`` instead — an empty label means "no label to apply;
    move the issue to the suggested status."
    """
    has_high = any(f.severity == SEVERITY_HIGH for f in ctx.findings)
    if has_high or _BLOCKED_MARKERS_RE.search(ctx.description):
        return ""
    return LABEL_SPEC_READY


def _suggest_status(ctx: _Context) -> str:
    """Return ``Backlog`` for agent-ready issues, ``Triage`` otherwise.

    Triage covers two cases the old workflow split into separate labels:
    issues missing template sections (was ``needs-spec``) and issues that
    explicitly call out a human/policy dependency (was ``agent-blocked``).
    """
    has_high = any(f.severity == SEVERITY_HIGH for f in ctx.findings)
    if has_high or _BLOCKED_MARKERS_RE.search(ctx.description):
        return STATUS_TRIAGE
    return STATUS_BACKLOG


def _estimate_tokens(ctx: _Context) -> dict[str, int]:
    title_chars = len(ctx.title)
    desc_chars = len(ctx.description)
    return {
        "title_chars": title_chars,
        "description_chars": desc_chars,
        "total_chars": title_chars + desc_chars,
        "estimated_tokens": (title_chars + desc_chars) // CHARS_PER_TOKEN,
        "noise_bytes_recoverable": ctx.noise_bytes,
    }


def _locate(text: str, char_offset: int) -> str:
    """Convert a char offset into a ``description:Lnn`` location string."""
    line = text.count("\n", 0, char_offset) + 1
    return f"description:L{line}"
