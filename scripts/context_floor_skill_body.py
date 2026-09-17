"""Single-skill body resolution for the context-efficiency epic (SG0).

Resolves one skill's body AST expression (however it was assembled --
concatenated literal chunks, an f-string, or the ``_claude_domain_skill()``
helper call) down to its ``description:`` frontmatter field. Split out of
``context_floor_skills.py`` (which owns discovering *which* expressions
exist) to keep both modules small; see that module's docstring.

Static resolution is inherently partial -- a body assembled at runtime
from calls or f-string interpolations cannot be fully reconstructed from
the AST. So resolution carries an ``elided`` flag (``ResolvedBody``)
saying whether it dropped anything, and the measurement layer refuses to
report a ``description`` that is missing or empty while that flag is set.
The rule this module exists to honour: never return a number derived from
text it knows it did not fully see.
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


@dataclass(frozen=True)
class ResolvedBody:
    """A skill body resolved to text, *plus whether that text is complete*.

    ``elided`` is ``True`` when the resolver dropped a segment it could not
    evaluate statically -- a runtime ``Call`` standing in for part of the
    body, or the interpolated tail of an f-string. The dropped segment
    contributes **nothing** to ``text``; it is not marked, padded, or
    placeheld, so ``text`` alone cannot tell a reader that anything is
    missing. That is exactly why the flag rides alongside it: any caller
    that turns ``text`` into a measurement must consult ``elided`` before
    believing a field it parsed out (see ``_skill_info_from_frontmatter``).
    """

    text: str
    elided: bool


def _joined_str_leading_literal(node: ast.JoinedStr) -> ResolvedBody:
    """The leading literal chunk of an f-string skill body -- only valid
    when the f-string *starts* with a plain string segment (frontmatter is
    never itself interpolated in this repo's skill templates).

    Everything after that first chunk is **dropped**, so an f-string with
    any further segment resolves ``elided=True``.
    """
    if (
        node.values
        and isinstance(node.values[0], ast.Constant)
        and isinstance(node.values[0].value, str)
    ):
        return ResolvedBody(node.values[0].value, elided=len(node.values) > 1)
    raise MeasurementError("f-string skill body starts with an interpolation, not a literal")


def _resolve_skill_body(node: ast.expr, symtab: dict[str, ast.expr]) -> ResolvedBody:
    """Resolve *node* to the string text it evaluates to, and say whether
    anything was lost doing so.

    Skill bodies are ``---`` / ``name: ...`` / ``---`` frontmatter followed
    by markdown, sometimes built by concatenating literal chunks with
    interpolated/imported calls in between (TAP-7755: a call spliced
    *between* two frontmatter-bearing literals, non-leftmost). This walks
    **both** operands of every ``+`` concatenation rather than stopping at
    the leftmost one, so a literal chunk that follows a call is still
    returned instead of silently dropped -- dropping it can truncate the
    frontmatter block before its ``description:`` line is ever reached.

    What is still lost, plainly: the call's **own** contribution. An
    elided ``Call`` resolves to the empty string, so ``"description: " +
    get_text()`` yields a ``description`` that parses as *present and
    empty* rather than as the text ``get_text()`` would have returned at
    runtime. Concatenating around a call therefore trades one silent
    truncation for a different silent gap, and text alone cannot
    distinguish "genuinely blank" from "blanked by elision". The returned
    ``ResolvedBody.elided`` flag is the only thing that can, and
    ``_skill_info_from_frontmatter`` refuses to report a measurement whose
    ``description`` is missing or empty while that flag is set.
    """
    return _resolve_literal_text(node, symtab, 0, strict=True)


def _leading_literal(node: ast.expr, symtab: dict[str, ast.expr]) -> str:
    """``_resolve_skill_body`` text only -- **discards the ``elided`` flag.**

    Safe only where the text is inspected, not measured. Anything that
    derives a number, a field value, or a report line from a skill body
    must call ``_resolve_skill_body`` and honour ``elided``; silently
    dropping it is how a loud ``MeasurementError`` became a wrong zero
    once already.
    """
    return _resolve_skill_body(node, symtab).text


def _resolve_literal_text(
    node: ast.expr, symtab: dict[str, ast.expr], depth: int, strict: bool
) -> ResolvedBody:
    """Implementation of ``_resolve_skill_body``.

    *strict* distinguishes the leftmost spine of the expression tree from
    everything reached through a ``BinOp.right`` operand. Off the spine
    (``strict=False``) an unresolvable ``Call`` contributes empty text and
    sets ``elided``, so the literal chunk(s) that follow it -- which may
    hold the ``description:`` line -- are still walked and concatenated
    rather than the whole resolution stopping dead at the call.

    On the leftmost spine (``strict=True``) an unresolvable ``Call``
    instead raises. Be clear about what that rule is and is not: it is
    **positional, not semantic**. A leftmost call followed by complete,
    self-contained, valid frontmatter would resolve perfectly well, and is
    refused anyway. It is kept deliberately, as a conservative
    over-approximation -- a call occupying the very first segment is the
    strongest available signal that the whole body, opening ``---``
    delimiter included, is assembled by a helper this resolver does not
    model, and refusing beats guessing at the top of a file whose shape is
    unknown. It is *not* a safety property, and nothing downstream should
    read it as one: the property that actually protects measurements is
    the ``elided`` flag, which covers calls in every position.
    """
    if depth > 50:
        raise MeasurementError("skill constant resolution exceeded max depth (possible cycle)")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return ResolvedBody(node.value, elided=False)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_literal_text(node.left, symtab, depth + 1, strict)
        right = _resolve_literal_text(node.right, symtab, depth + 1, strict=False)
        return ResolvedBody(left.text + right.text, elided=left.elided or right.elided)
    if isinstance(node, ast.Name):
        if node.id not in symtab:
            raise MeasurementError(f"unresolved skill-body constant reference: {node.id}")
        return _resolve_literal_text(symtab[node.id], symtab, depth + 1, strict)
    if isinstance(node, ast.JoinedStr):
        return _joined_str_leading_literal(node)
    if isinstance(node, ast.Call) and not strict:
        return ResolvedBody("", elided=True)
    raise MeasurementError(f"unsupported skill-body expression: {ast.dump(node)[:80]}")


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


def _parse_skill_frontmatter(body: str) -> dict[str, str]:
    """Minimal frontmatter parser for the fixed, hand-authored SKILL.md
    shapes in this repo: single-line ``key: value`` and ``key: >-``/``key:
    |-`` folded/literal block scalars with 2-space-indented continuation
    lines. Not a general YAML parser -- sufficient for these templates.
    """
    lines = body.splitlines()
    start, end = _frontmatter_bounds(lines)
    fm_lines = lines[start + 1 : end] if end is not None else lines[start + 1 :]

    result: dict[str, str] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line or line[0] in " \t-" or ":" not in line:
            i += 1
            continue
        key, _, remainder = line.partition(":")
        key = key.strip()
        remainder = remainder.strip()
        if remainder in (">-", ">", "|-", "|"):
            result[key], i = _fold_block_scalar(fm_lines, i + 1)
        else:
            result[key] = remainder.strip('"')
            i += 1
    return result


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


def _skill_info_from_frontmatter(
    name: str, expr: ast.expr, symtab: dict[str, ast.expr]
) -> SkillInfo:
    """Parse one resolved skill body into a ``SkillInfo``, refusing any
    result an elision could have corrupted.

    The guard is narrow on purpose. An elision **somewhere** in the body is
    routine and harmless -- calls splice markdown into these templates all
    the time -- so a non-empty ``description`` parsed out of elided text is
    accepted: the measured field itself survived intact. What is refused is
    the one combination where the elision and the measurement overlap, a
    ``description`` that is missing or empty while text was dropped. There
    the blank is unattributable: it may be a genuinely blank field, or it
    may be the elided call's return value, and no measurement should be
    reported from text the resolver knows it did not fully see. Only
    ``description`` is guarded this way, because only ``description`` is
    the measured quantity; ``context`` and ``disable-model-invocation`` are
    booleans read from the same text and carry the same caveat.
    """
    resolved = _resolve_skill_body(expr, symtab)
    frontmatter = _parse_skill_frontmatter(resolved.text)
    fm_description = frontmatter.get("description")
    if fm_description is None:
        raise MeasurementError(f"{name}: no description field in frontmatter")
    if resolved.elided and not fm_description:
        raise MeasurementError(
            f"{name}: description is empty and part of the skill body was elided "
            "(an unresolvable call or f-string interpolation contributed no text) "
            "-- the real description may be exactly what was dropped; refusing to "
            "measure a body this resolver did not fully see"
        )
    return SkillInfo(
        name=name,
        description=fm_description,
        context_fork=frontmatter.get("context", "").strip() == "fork",
        disable_model_invocation=frontmatter.get("disable-model-invocation", "").strip().lower()
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
