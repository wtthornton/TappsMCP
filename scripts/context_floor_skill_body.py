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


def _joined_str_leading_literal(node: ast.JoinedStr) -> str:
    """The leading literal chunk of an f-string skill body -- only valid
    when the f-string *starts* with a plain string segment (frontmatter is
    never itself interpolated in this repo's skill templates)."""
    if (
        node.values
        and isinstance(node.values[0], ast.Constant)
        and isinstance(node.values[0].value, str)
    ):
        return node.values[0].value
    raise MeasurementError("f-string skill body starts with an interpolation, not a literal")


def _leading_literal(node: ast.expr, symtab: dict[str, ast.expr], depth: int = 0) -> str:
    """Resolve *node* to the leading string-literal text it evaluates to.

    Skill bodies are ``---`` / ``name: ...`` / ``---`` frontmatter followed
    by markdown, sometimes built by concatenating a leading literal with later
    interpolated/imported chunks (the body after frontmatter). Frontmatter
    -- all this script needs -- always lives in the leftmost literal
    segment, so only that segment needs resolving: the rest of the
    concatenation (markdown body, f-string interpolations) is never
    inspected.
    """
    if depth > 50:
        raise MeasurementError("skill constant resolution exceeded max depth (possible cycle)")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _leading_literal(node.left, symtab, depth + 1)
    if isinstance(node, ast.Name):
        if node.id not in symtab:
            raise MeasurementError(f"unresolved skill-body constant reference: {node.id}")
        return _leading_literal(symtab[node.id], symtab, depth + 1)
    if isinstance(node, ast.JoinedStr):
        return _joined_str_leading_literal(node)
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
    body = _leading_literal(expr, symtab)
    frontmatter = _parse_skill_frontmatter(body)
    fm_description = frontmatter.get("description")
    if fm_description is None:
        raise MeasurementError(f"{name}: no description field in frontmatter")
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
