"""Single-skill body resolution for the context-efficiency epic (SG0).

Resolves one skill's body AST expression (however it was assembled --
concatenated literal chunks, an f-string, or the ``_claude_domain_skill()``
helper call) down to its ``description:`` frontmatter field. Split out of
``context_floor_skills.py`` (which owns discovering *which* expressions
exist) to keep both modules small; see that module's docstring.

Static resolution is inherently partial. Two constructs cannot be evaluated
from the AST alone and are therefore **elided**:

1. an unresolvable ``Call`` reached through a ``+`` concatenation off the
   leftmost spine (``"header" + build_body() + "footer"``), and
2. every interpolated segment of an f-string (``f"...{x}..."``).

Elision is not tracked beside the text -- it is written **into** the text.
Each elided segment is replaced by ``_ELIDED_SENTINEL``, a fixed string
built from Unicode private-use code points that cannot occur in a
hand-authored SKILL.md. The sentinel then flows through frontmatter parsing
exactly like any other characters, so the question "did the loss land inside
a field I am about to measure?" is answered by ordinary substring search on
the parsed result rather than by a flag the parser cannot position.

``_skill_info_from_frontmatter`` refuses to build a ``SkillInfo`` when the
sentinel survives into any frontmatter **key**, or into any of the three
frontmatter **values** a ``SkillInfo`` is derived from (``description``,
``context``, ``disable-model-invocation``). An elision anywhere else -- the
markdown body, a ``model:`` line, the text after the closing ``---`` -- is
routine and resolves normally, because the measured fields survived intact.

Consequence worth stating plainly: **no sentinel can ever reach a returned
value or a byte count**, because every path on which one could have reached
``SkillInfo.description`` raises instead. The rule this module exists to
honour: never return a number derived from text it knows it did not fully
see.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from context_floor_core import MeasurementError

# U+E000..U+F8FF is the Unicode Basic Multilingual Plane Private Use Area:
# no character is assigned there, so nothing a human types into a SKILL.md
# frontmatter -- ASCII prose, markdown punctuation, the occasional accented
# word or emoji (emoji live in the astral planes, not here) -- can contain
# one. Wrapping a fixed tag in two of them makes the sentinel simultaneously
# (a) impossible to author by accident, (b) greppable as plain text, and
# (c) inert to every transformation ``_parse_skill_frontmatter`` applies:
# it holds no newline (so it can neither split a line nor forge a ``---``
# delimiter), no ``:`` (so it cannot forge a key/value split), no ``"``
# (so ``strip('"')`` cannot erode it), no leading ``-`` or whitespace (so
# neither ``strip()`` nor the ``line[0] in " \t-"`` skip can swallow it).
_ELIDED_SENTINEL = "TAPPS-ELIDED-3f6a1c"

# The frontmatter values ``SkillInfo`` is built from. A sentinel surviving
# into one of these means the elision landed inside the span of a field this
# module reports, which is exactly the condition that must refuse.
_MEASURED_FIELDS = ("description", "context", "disable-model-invocation")


@dataclass
class SkillInfo:
    name: str
    description: str
    context_fork: bool
    disable_model_invocation: bool

    @property
    def description_bytes(self) -> int:
        return len(self.description.encode("utf-8"))


def _joined_str_text(node: ast.JoinedStr) -> str:
    """Resolve an f-string skill body, substituting ``_ELIDED_SENTINEL`` for
    every interpolated segment.

    Literal segments contribute their own text verbatim; each
    ``FormattedValue`` -- including one whose value is itself a nested
    f-string -- contributes one sentinel, because its runtime text is not
    knowable from the AST. Unlike the pre-sentinel implementation this does
    **not** stop at the leading literal: a literal chunk following an
    interpolation is real frontmatter text and dropping it truncated the
    block (the same defect class as TAP-7755 in the concatenation channel).

    An f-string that *starts* with an interpolation still raises, and the
    reason is mechanical rather than stylistic: the opening ``---``
    delimiter would then be preceded by sentinel characters on its own line,
    ``_frontmatter_bounds`` would no longer recognise it, and the block would
    be located from the wrong delimiter. Refusing names that situation
    accurately instead of mis-parsing it.
    """
    if not (
        node.values
        and isinstance(node.values[0], ast.Constant)
        and isinstance(node.values[0].value, str)
    ):
        raise MeasurementError("f-string skill body starts with an interpolation, not a literal")
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append(_ELIDED_SENTINEL)
    return "".join(parts)


def _resolve_skill_body(node: ast.expr, symtab: dict[str, ast.expr]) -> str:
    """Resolve *node* to the string text it evaluates to, with every segment
    that could not be evaluated statically replaced by ``_ELIDED_SENTINEL``.

    Skill bodies are ``---`` / ``name: ...`` / ``---`` frontmatter followed
    by markdown, sometimes built by concatenating literal chunks with
    interpolated/imported calls in between (TAP-7755: a call spliced
    *between* two frontmatter-bearing literals, non-leftmost). This walks
    **both** operands of every ``+`` concatenation rather than stopping at
    the leftmost one, so a literal chunk that follows a call is still
    returned instead of silently dropped -- dropping it can truncate the
    frontmatter block before its ``description:`` line is ever reached.

    The returned text is therefore *positionally faithful*: wherever the
    resolver could not see the real characters, the sentinel occupies their
    place. Callers must not measure, return, or report this text without
    first checking that no sentinel survives into the part they care about;
    ``_skill_info_from_frontmatter`` is the one caller that does so.
    """
    return _resolve_literal_text(node, symtab, 0, strict=True)


def _resolve_literal_text(
    node: ast.expr, symtab: dict[str, ast.expr], depth: int, strict: bool
) -> str:
    """Implementation of ``_resolve_skill_body``.

    *strict* distinguishes the leftmost spine of the expression tree from
    everything reached through a ``BinOp.right`` operand. Off the spine
    (``strict=False``) an unresolvable ``Call`` contributes one sentinel, so
    the literal chunk(s) that follow it -- which may hold the
    ``description:`` line -- are still walked and concatenated rather than
    the whole resolution stopping dead at the call.

    On the leftmost spine (``strict=True``) an unresolvable ``Call`` instead
    raises. The rule is **positional, not semantic**: a leftmost call
    followed by complete, self-contained, valid frontmatter would evaluate
    fine at runtime and is refused anyway. It is kept because substituting a
    sentinel there would place sentinel characters ahead of the opening
    ``---`` on its own line, which ``_frontmatter_bounds`` would then fail to
    recognise as a delimiter -- the block would be located from the *closing*
    ``---`` instead and yield an empty, silently wrong frontmatter. Raising
    at the call site names that situation; sentinel substitution could only
    mis-parse it. Note this is a parser-shape constraint, not the safety
    property: what protects measurements is the sentinel, which covers calls
    in every other position.
    """
    if depth > 50:
        raise MeasurementError("skill constant resolution exceeded max depth (possible cycle)")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_literal_text(node.left, symtab, depth + 1, strict)
        right = _resolve_literal_text(node.right, symtab, depth + 1, strict=False)
        return left + right
    if isinstance(node, ast.Name):
        if node.id not in symtab:
            raise MeasurementError(f"unresolved skill-body constant reference: {node.id}")
        return _resolve_literal_text(symtab[node.id], symtab, depth + 1, strict)
    if isinstance(node, ast.JoinedStr):
        return _joined_str_text(node)
    if isinstance(node, ast.Call) and not strict:
        return _ELIDED_SENTINEL
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

    Sentinel-agnostic by design: ``_ELIDED_SENTINEL`` is ordinary text here
    and is neither produced nor consumed. It survives into whichever key or
    value it landed in, which is what lets the caller decide positionally
    whether the loss overlapped a field it reports.
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
    result whose reported fields overlap an elided segment.

    The test is **positional**, and that is the whole point: it does not ask
    whether an elision happened (one usually did -- calls splice markdown
    into these templates constantly), nor whether the parsed value came out
    empty (a partly-elided value is just as unmeasurable as a wholly-elided
    one, and ``'prefix-' + <elided> + '-suffix'`` parses out non-empty). It
    asks only whether ``_ELIDED_SENTINEL`` -- which occupies exactly the
    character positions the resolver could not see -- survived into

    * any frontmatter **key**, meaning the loss straddled a ``key: value``
      boundary and no field in this block can be identified reliably; or
    * any of ``_MEASURED_FIELDS``, the three values a ``SkillInfo`` is
      derived from.

    Either way the number or flag that would be reported is partly invented,
    so it raises instead. An elision that lands anywhere else -- a ``model:``
    line, the markdown body, past the closing ``---`` -- leaves every
    reported field intact and resolves normally.

    Because every sentinel-bearing path raises, a returned ``SkillInfo``
    provably contains no sentinel in any field and no sentinel byte in
    ``description_bytes``.
    """
    body = _resolve_skill_body(expr, symtab)
    frontmatter = _parse_skill_frontmatter(body)

    for key in frontmatter:
        if _ELIDED_SENTINEL in key:
            raise MeasurementError(
                f"{name}: an elided segment landed inside a frontmatter field NAME -- an "
                "unresolvable call or f-string interpolation straddles a 'key: value' "
                "boundary, so no field in this frontmatter block can be identified "
                "reliably; refusing to measure a body this resolver did not fully see"
            )

    fm_description = frontmatter.get("description")
    if fm_description is None:
        raise MeasurementError(f"{name}: no description field in frontmatter")

    for field in _MEASURED_FIELDS:
        if _ELIDED_SENTINEL in frontmatter.get(field, ""):
            raise MeasurementError(
                f"{name}: the '{field}' frontmatter field contains an elided segment -- part "
                "of its value comes from an unresolvable call or f-string interpolation, so "
                "the real value may be exactly what was dropped; refusing to measure a body "
                "this resolver did not fully see"
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
