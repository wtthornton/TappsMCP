"""Single-skill body resolution for the context-efficiency epic (SG0).

Resolves one skill's body AST expression (however it was assembled --
concatenated literal chunks, an f-string, or the ``_claude_domain_skill()``
helper call) down to its ``description:`` frontmatter field. Split out of
``context_floor_skills.py`` (which owns discovering *which* expressions
exist) to keep both modules small; see that module's docstring.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from context_floor_core import MeasurementError


@dataclass
class SkillInfo:
    name: str
    description: str
    context_fork: bool
    disable_model_invocation: bool

    @property
    def description_bytes(self) -> int:
        return len(self.description.encode("utf-8"))


# Marks a body segment that cannot be evaluated statically -- a helper call,
# an out-of-module name, an f-string interpolation.
#
# The codepoints are Unicode Private Use Area. The guard tests for the full
# nine-character marker, not the codepoint alone: a lone U+E000 (or any other
# PUA use) in a hand-authored SKILL.md is accepted, and only a body containing
# the literal marker sequence is refused. That is the declared trade-off, not
# a guarantee of no collision.
#
# The marker has to survive every positional decision the frontmatter parser
# makes about *where* a field ends, because the guard runs after that
# partitioning and only sees what the partition attributes to a measured
# field. Most such decisions cannot read it: it cannot strip to ``---``
# (``_frontmatter_bounds``), it cannot form a key token (``_opens_key``),
# frontmatter lines it lands on that no field's span covers are rejected
# outright (this does not extend to markdown body lines below the closing
# ``---``, which no span covers either but which are correctly not
# rejected), and a shadowed duplicate key keeps its raw span
# (``_parse_skill_frontmatter_fields``).
#
# One decision CAN move a span boundary past the marker: ``body.splitlines()``
# (below) breaks on ``\x0b \x0c \x1c \x1d \x1e`` in addition to ``\n``, and a
# marker straddling one of those breaks can land on a line that opens a new,
# unmeasured key. The gap that would open is closed by pyyaml, not by this
# code: pyyaml refuses to load any document containing those five characters
# at all ("unacceptable character #x000b: special characters are not
# allowed"), so no valid, hand-authored SKILL.md can reach this path.
_ELISION = "\ue000elided\ue000"


def _resolve_body_text(node: ast.expr, symtab: dict[str, ast.expr], depth: int = 0) -> str:
    """Resolve *node* to the skill-body text it evaluates to.

    Skill bodies are ``---`` / ``name: ...`` / ``---`` frontmatter followed by
    markdown, often assembled by concatenating literal chunks with spliced-in
    ones (a helper call, an imported constant, an f-string interpolation).

    Every segment is walked, in source order. A segment that cannot be
    evaluated statically resolves to ``_ELISION`` rather than being dropped or
    stopped at, so the text that follows it is still recovered *and* its
    position is still recorded. Dropping the position is what defeated the
    five earlier fixes for TAP-7755: a guard that reads the parsed value
    inherits every position the parser discarded.
    """
    if depth > 50:
        raise MeasurementError("skill constant resolution exceeded max depth (possible cycle)")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _resolve_body_text(node.left, symtab, depth + 1) + _resolve_body_text(
            node.right, symtab, depth + 1
        )
    if isinstance(node, ast.Name) and node.id in symtab:
        return _resolve_body_text(symtab[node.id], symtab, depth + 1)
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
            else _ELISION
            for value in node.values
        )
    return _ELISION


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int | None]:
    """Return (start, end) line indices of the ``---``-delimited block.
    ``end`` is ``None`` when a closing delimiter never appears (the body
    after frontmatter was spliced in via string concatenation elsewhere;
    everything through end-of-text is treated as frontmatter, which is
    always enough to find the fields this script needs)."""
    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip() != "---":
            continue
        if start is None:
            start = i
        else:
            return start, i
    if start is None:
        raise MeasurementError("no frontmatter start delimiter ('---') found")
    return start, None


def _fold_block_scalar(fm_lines: list[str], continuation_start: int) -> tuple[str, int]:
    """Fold a YAML ``>-``/``|-`` block scalar's indented continuation lines
    into one space-joined string; return (folded_text, next_line_index)."""
    continuation: list[str] = []
    j = continuation_start
    while j < len(fm_lines) and (fm_lines[j].startswith("  ") or not fm_lines[j].strip()):
        continuation.append(fm_lines[j].strip())
        j += 1
    return " ".join(part for part in continuation if part), j


@dataclass(frozen=True)
class _Field:
    """One frontmatter field: its parsed ``value`` and the verbatim ``raw``
    frontmatter lines that value was read from."""

    value: str
    raw: str


def _opens_key(line: str) -> bool:
    """Whether *line* starts a new ``key: ...`` frontmatter field.

    The key token is the text before the first ``:``. A token carrying an
    elision marker does not open a key: the marker stands for text this script
    could not read, so neither the token nor the ``:`` after it is known to be
    what it looks like. Reading it as a key is what refuted the previous fix --
    ``<marker>: words`` spliced into a ``description: >-`` continuation opened
    a bogus field, which moved ``description``'s span boundary up and carried
    the marker out of the one span the guard inspects.
    """
    key, separator, _ = line.partition(":")
    return bool(separator) and bool(key) and key[0] not in " \t-" and _ELISION not in key


def _reject_unattributed_elisions(lines: list[str], start: int, preamble: list[str]) -> None:
    """Refuse an elision marker that no field's span can claim.

    The per-field guard only ever sees text the span partition attributed to a
    field, so a marker the partition drops is a marker nobody checks. Two
    regions are dropped by construction: everything at or above the opening
    ``---``, and the frontmatter lines above the first key. A marker stands for
    text this script could not read, and text in either region could be the
    ``---`` or the ``description:`` that decides what gets measured -- so
    neither region may contain one.
    """
    for region, where in (
        (lines[: start + 1], "at or above the frontmatter start delimiter"),
        (preamble, "between the frontmatter start delimiter and the first key"),
    ):
        if any(_ELISION in line for line in region):
            raise MeasurementError(
                f"frontmatter contains a segment this script cannot resolve statically "
                f"{where}, where it belongs to no field's span; the measured value "
                f"would be unguarded"
            )


def _parse_skill_frontmatter_fields(body: str) -> dict[str, _Field]:
    """Minimal frontmatter parser for the fixed, hand-authored SKILL.md
    shapes in this repo: single-line ``key: value`` and ``key: >-``/``key:
    |-`` folded/literal block scalars with 2-space-indented continuation
    lines. Not a general YAML parser -- sufficient for these templates.

    Each field also carries its raw span: its own ``key:`` line plus every
    line up to the next line that opens a key. The span deliberately does
    *not* stop where ``_fold_block_scalar`` stops. Folding continues only
    while a line is indented or blank, so a spliced segment occupying its own
    line ends folding and is excluded from the value -- which is precisely how
    the guard-on-the-parsed-value fix for TAP-7755 was refuted.

    The span is the field's footprint as this partition computes it, which is
    not the same as its footprint in the source text: the partition can only
    attribute a line to the nearest key at or above it. What the caller's
    guard relies on is narrower and is what the three steps below establish --
    that no elision marker can be attributed *away* from the field it sits in.
    A marker cannot open a key (``_opens_key``), so it can never push a span
    boundary up past itself; a line no span covers is refused outright
    (``_reject_unattributed_elisions``); and a key that repeats keeps the raw
    span of every occurrence, so a shadowed elision is not dropped with the
    value it shadowed.
    """
    lines = body.splitlines()
    start, end = _frontmatter_bounds(lines)
    fm_lines = lines[start + 1 : end] if end is not None else lines[start + 1 :]

    key_starts = [i for i, line in enumerate(fm_lines) if _opens_key(line)]
    _reject_unattributed_elisions(
        lines, start, fm_lines[: key_starts[0]] if key_starts else fm_lines
    )

    result: dict[str, _Field] = {}
    for n, i in enumerate(key_starts):
        span_end = key_starts[n + 1] if n + 1 < len(key_starts) else len(fm_lines)
        key, _, remainder = fm_lines[i].partition(":")
        remainder = remainder.strip()
        if remainder in (">-", ">", "|-", "|"):
            value, _next = _fold_block_scalar(fm_lines, i + 1)
        else:
            value = remainder.strip('"')
        key = key.strip()
        raw = "\n".join(fm_lines[i:span_end])
        shadowed = result.get(key)
        # A repeated key reports its last value, as a YAML loader would, but
        # accumulates every occurrence's raw span. Overwriting the span instead
        # let an elision in the shadowed occurrence vanish with it.
        result[key] = _Field(value=value, raw=f"{shadowed.raw}\n{raw}" if shadowed else raw)
    return result


def _parse_skill_frontmatter(body: str) -> dict[str, str]:
    """``_parse_skill_frontmatter_fields`` without the raw spans -- the shape
    ``context_floor_skills._skill_info_from_asset`` consumes."""
    return {key: field.value for key, field in _parse_skill_frontmatter_fields(body).items()}


def _domain_skill_description(skill_name: str, call: ast.Call) -> str:
    """Extract the description passed to the ``_claude_domain_skill(name,
    description, domain, ...)`` helper (tapps-domain-frontend/security/
    testing build their SKILL.md via an f-string-returning function, not a
    plain dict literal, so the frontmatter can't be parsed out of a
    resolved body string; the description is read directly from the call
    argument instead).
    """
    if len(call.args) >= 2:
        node: ast.expr = call.args[1]
    else:
        keyword = next((kw for kw in call.keywords if kw.arg == "description"), None)
        if keyword is None:
            raise MeasurementError(f"{skill_name}: _claude_domain_skill call has no description")
        node = keyword.value
    value = ast.literal_eval(node)
    if not isinstance(value, str):
        raise MeasurementError(f"{skill_name}: description argument is not a string literal")
    return value


def _skill_info_from_domain_call(name: str, call: ast.Call) -> SkillInfo:
    description = _domain_skill_description(name, call)
    return SkillInfo(
        name=name, description=description, context_fork=False, disable_model_invocation=False
    )


# The frontmatter fields that end up in a ``SkillInfo``. An elision anywhere
# in one of these fields' raw spans means the value this script would report
# is a truncation of the real one, so it must fail loudly instead.
#
# The converse is a tolerance, not a proof: an elision attributed to an
# *unmeasured* field (``name:``, or any line below it and above the next key)
# is accepted, and the text it stands for could in principle itself contain
# frontmatter structure -- a second ``description:``, or a ``---`` that ends
# the block early. That is accepted knowingly, because resolving *past* such a
# splice to reach a later ``description:`` is the behaviour TAP-7755 asks for;
# refusing it would refuse the issue's own headline case. It is bounded: over
# this repo's tree the resolver has zero live invocations (every skill is read
# from its ``.md`` asset or the ``_claude_domain_skill`` call), so the
# tolerance currently applies to no measured skill at all.
_MEASURED_FIELDS = ("description", "context", "disable-model-invocation")


def _reject_elided_fields(name: str, fields: dict[str, _Field]) -> None:
    for key in _MEASURED_FIELDS:
        field = fields.get(key)
        if field is not None and _ELISION in field.raw:
            raise MeasurementError(
                f"{name}: {key} frontmatter field spans a segment this script "
                f"cannot resolve statically; its measured value would be a truncation"
            )


def _skill_info_from_frontmatter(
    name: str, expr: ast.expr, symtab: dict[str, ast.expr]
) -> SkillInfo:
    body = _resolve_body_text(expr, symtab)
    fields = _parse_skill_frontmatter_fields(body)
    _reject_elided_fields(name, fields)
    description = fields.get("description")
    if description is None:
        raise MeasurementError(f"{name}: no description field in frontmatter")
    values = {key: field.value for key, field in fields.items()}
    return SkillInfo(
        name=name,
        description=description.value,
        context_fork=values.get("context", "").strip() == "fork",
        disable_model_invocation=values.get("disable-model-invocation", "").strip().lower()
        == "true",
    )


def resolve_skill_info(name: str, expr: ast.expr, symtab: dict[str, ast.expr]) -> SkillInfo:
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "_claude_domain_skill"
    ):
        return _skill_info_from_domain_call(name, expr)
    return _skill_info_from_frontmatter(name, expr, symtab)
