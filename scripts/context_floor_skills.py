"""Skill-description measurement for the context-efficiency epic (SG0).

Sums the ``description:`` frontmatter field of every skill shipped by
tapps-mcp's own template modules -- that string is what loads into every
Claude Code session's skill listing, regardless of whether the skill body
itself is ever invoked.

Discovers *which* skill-body AST expressions exist (dict literal, merged-in
companion dicts, individual subscript overrides); resolving a single
expression down to its description lives in ``context_floor_skill_body.py``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from context_floor_core import _PIPELINE_DIR, MeasurementError, _assign_target, _parse
from context_floor_skill_body import SkillInfo, _parse_skill_frontmatter, resolve_skill_info

# Skill-body extraction (plugin-dist program, Lanes 1-2): the templated
# CLAUDE_SKILLS bodies now live as package-data ``.md`` files under
# ``assets/claude_skills/`` and the dict literal holds
# ``_load_claude_skill("<name>")`` calls instead of inline string literals
# (see ``platform_skills.py``'s module docstring for that section). The same
# shape now also arrives via ``CLAUDE_SKILLS.update(CLAUDE_DOMAIN_SKILLS)``
# (platform_domain_skills.py's own, separately-defined ``_load_claude_skill``
# -- same name, same ``assets/claude_skills/`` layout, different module,
# matched here purely by call shape) and via the post-hoc CLAUDE_SKILLS
# subscript assignments. ``CLAUDE_DOCS_SKILLS``
# (platform_docs_automation.py) uses the sibling ``_load_claude_docs_skill``
# loader reading from ``assets/claude_docs_skills/`` instead.
#
# A bare AST literal-resolution over any of these entries can no longer
# recover the frontmatter -- there is no literal text left in the module to
# resolve, only a file reference -- so this script reads the referenced
# ``.md`` file directly instead of asking ``context_floor_skill_body`` to
# parse a call it does not know about. The substitution each loader applies
# at import time (``{{model:<role>}}`` / ``{{docs_prefix}}`` -> a resolved
# value) never touches the ``description:`` frontmatter field this script
# measures, so the raw file content is sufficient.
_SKILL_ASSET_SUBDIR = ("assets", "claude_skills")
_DOCS_SKILL_ASSET_SUBDIR = ("assets", "claude_docs_skills")


def _call_arg_str(node: ast.expr, func_name: str) -> str | None:
    """If *node* is ``<func_name>("literal")``, return ``"literal"``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == func_name
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None


def _asset_load_name(node: ast.expr) -> str | None:
    """If *node* is ``_load_claude_skill("name")``, return ``"name"``."""
    return _call_arg_str(node, "_load_claude_skill")


def _docs_skill_asset_load_name(node: ast.expr) -> str | None:
    """If *node* is ``_load_claude_docs_skill("name")``, return ``"name"``."""
    return _call_arg_str(node, "_load_claude_docs_skill")


def _skill_info_from_asset(
    skill_name: str, asset_name: str, pipeline_dir: Path, subdir: tuple[str, ...] = _SKILL_ASSET_SUBDIR
) -> SkillInfo:
    """Resolve a skill body stored as a package-data ``.md`` file."""
    asset_path = pipeline_dir.joinpath(*subdir, f"{asset_name}.md")
    if not asset_path.exists():
        raise MeasurementError(f"{skill_name}: skill asset file not found: {asset_path}")
    body = asset_path.read_text(encoding="utf-8")
    frontmatter = _parse_skill_frontmatter(body)
    fm_description = frontmatter.get("description")
    if fm_description is None:
        raise MeasurementError(f"{skill_name}: no description field in frontmatter")
    return SkillInfo(
        name=skill_name,
        description=fm_description,
        context_fork=frontmatter.get("context", "").strip() == "fork",
        disable_model_invocation=frontmatter.get("disable-model-invocation", "").strip().lower()
        == "true",
    )


def _discover_sibling_modules(main_file: Path, pipeline_dir: Path) -> set[Path]:
    """Follow ``from tapps_mcp.pipeline.<mod> import ...`` statements in
    *main_file* to the sibling modules that actually define the imported
    skill-body constants (skill bodies are split across companion files
    for size, e.g. ``platform_skill_orchestration.py``)."""
    tree = _parse(main_file)
    files = {main_file}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("tapps_mcp.pipeline.")
        ):
            candidate = pipeline_dir / f"{node.module.rsplit('.', 1)[-1]}.py"
            if candidate.exists():
                files.add(candidate)
    return files


def _build_symbol_table(files: set[Path]) -> dict[str, ast.expr]:
    table: dict[str, ast.expr] = {}
    for path in files:
        for node in _parse(path).body:
            name, value = _assign_target(node)
            if name is not None and value is not None:
                table[name] = value
    return table


def _dict_literal_entries(node: ast.Dict) -> dict[str, ast.expr]:
    entries: dict[str, ast.expr] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            entries[key.value] = value
    return entries


def _resolve_dict_literal(name: str, files: set[Path]) -> ast.Dict | None:
    for path in files:
        for node in _parse(path).body:
            target, value = _assign_target(node)
            if target == name and isinstance(value, ast.Dict):
                return value
    return None


def _as_dict_update_arg(node: ast.stmt, dict_name: str) -> ast.Name | None:
    """If *node* is the statement ``<dict_name>.update(<Name>)``, return
    the ``Name`` node being merged in; otherwise ``None``."""
    if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
        return None
    call = node.value
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "update"):
        return None
    if not (isinstance(call.func.value, ast.Name) and call.func.value.id == dict_name):
        return None
    if call.args and isinstance(call.args[0], ast.Name):
        return call.args[0]
    return None


def _as_dict_subscript_assign(node: ast.stmt, dict_name: str) -> tuple[str, ast.expr] | None:
    """If *node* is the statement ``<dict_name>["key"] = value``, return
    ``(key, value)``; otherwise ``None``."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
        return None
    target = node.targets[0]
    if not (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)):
        return None
    if target.value.id != dict_name:
        return None
    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
        return target.slice.value, node.value
    return None


def _collect_skill_dict(main_file: Path, dict_name: str, files: set[Path]) -> dict[str, ast.expr]:
    """Simulate ``DICT: dict[str, str] = {...}`` + ``DICT.update(OTHER)`` +
    ``DICT["key"] = value`` module-level statements, in source order, to
    build the final skill-name -> body-expression mapping that exists at
    import time -- the same set that actually deploys to ``.claude/skills/``.
    """
    collected: dict[str, ast.expr] = {}
    for node in _parse(main_file).body:
        target, value = _assign_target(node)
        if target == dict_name and isinstance(value, ast.Dict):
            collected.update(_dict_literal_entries(value))
            continue
        update_arg = _as_dict_update_arg(node, dict_name)
        if update_arg is not None:
            other = _resolve_dict_literal(update_arg.id, files)
            if other is not None:
                collected.update(_dict_literal_entries(other))
            continue
        subscript_entry = _as_dict_subscript_assign(node, dict_name)
        if subscript_entry is not None:
            key, entry_value = subscript_entry
            collected[key] = entry_value
    return collected


def _collect_skill_set(main_file: Path, dict_name: str) -> dict[str, SkillInfo]:
    files = _discover_sibling_modules(main_file, _PIPELINE_DIR)
    symtab = _build_symbol_table(files)
    raw = _collect_skill_dict(main_file, dict_name, files)
    result: dict[str, SkillInfo] = {}
    for name, expr in raw.items():
        asset_name = _asset_load_name(expr)
        docs_asset_name = _docs_skill_asset_load_name(expr)
        if asset_name is not None:
            result[name] = _skill_info_from_asset(name, asset_name, main_file.parent)
        elif docs_asset_name is not None:
            result[name] = _skill_info_from_asset(
                name, docs_asset_name, main_file.parent, subdir=_DOCS_SKILL_ASSET_SUBDIR
            )
        else:
            result[name] = resolve_skill_info(name, expr, symtab)
    return result


@dataclass
class SkillsResult:
    description_bytes: int
    skills: list[SkillInfo]


def measure_skills() -> SkillsResult:
    """Sum the ``description:`` frontmatter field of every skill shipped by
    tapps-mcp's own template modules -- ``platform_skills.py`` (the base
    catalog + domain/flow skills merged in at import time) and
    ``platform_docs_automation.py`` (the docs-mcp companion skills, a
    separate template module not imported by ``platform_skills.py``).
    Third-party skills (e.g. the Linear plugin's ``linear``) are not
    TappsMCP's to measure and are excluded.
    """
    tapps_file = _PIPELINE_DIR / "platform_skills.py"
    docs_file = _PIPELINE_DIR / "platform_docs_automation.py"
    if not tapps_file.exists():
        raise MeasurementError(f"expected skill template module not found: {tapps_file}")
    if not docs_file.exists():
        raise MeasurementError(f"expected skill template module not found: {docs_file}")

    all_skills: dict[str, SkillInfo] = {}
    all_skills.update(_collect_skill_set(tapps_file, "CLAUDE_SKILLS"))
    all_skills.update(_collect_skill_set(docs_file, "CLAUDE_DOCS_SKILLS"))

    skills = sorted(all_skills.values(), key=lambda s: s.name)
    total_bytes = sum(s.description_bytes for s in skills)
    return SkillsResult(description_bytes=total_bytes, skills=skills)
