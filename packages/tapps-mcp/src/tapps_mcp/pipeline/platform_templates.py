"""Project-root scaffolded templates placed by ``tapps_init`` and refreshed by ``tapps_upgrade``.

TAP-7423: a first-class **template** artifact category, distinct from a skill's
companion assets (:mod:`tapps_mcp.pipeline.skill_asset_policy`). That path was
considered and rejected for this content:

1. A skill companion lands under ``.claude/skills/<name>/assets/`` — not
   somewhere a project naturally looks for a template.
2. No companion asset of any skill is ever backed up by
   :func:`tapps_mcp.pipeline.upgrade_backup.collect_upgrade_targets`, so
   ``tapps-mcp rollback`` could never restore a customised copy.
3. The companion marker wrapper
   (:func:`tapps_mcp.pipeline.skill_asset_policy.wrap_asset`) writes its
   ``BEGIN``/policy-header comment as the first bytes of the file, ahead of
   any real document content — untested for ``.html`` and a bad shape for a
   file a consumer may open directly.

Templates instead get a plain **overwrite-with-report** policy: the packaged
body is written verbatim (no header, no marker — nothing precedes the
template's own content), and :func:`tapps_mcp.pipeline.skill_asset_policy.plan_overwrite_report`
names any on-disk customisation before it is replaced, exactly as it already
does for non-delimitable skill companions.

The template itself ships as a package file asset under
``src/tapps_mcp/templates/`` (the ``prompts/`` precedent —
:mod:`tapps_mcp.prompts.prompt_loader`), loaded via ``importlib.resources``
with the same ``sys.frozen`` fallback for PyInstaller builds.
"""

from __future__ import annotations

import importlib.resources
import sys
from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.skill_asset_policy import plan_overwrite_report

_PACKAGE = "tapps_mcp.templates"

ONE_PAGER_REL_PATH = "docs/templates/one-pager.html"


def _read_template_resource(filename: str) -> str:
    """Read a text resource from the ``tapps_mcp.templates`` package.

    Falls back to ``Path(__file__)``-based resolution when running inside a
    PyInstaller frozen executable where ``importlib.resources`` cannot locate
    package data files — mirrors :func:`tapps_mcp.prompts.prompt_loader._read_resource`.
    """
    if getattr(sys, "frozen", False):
        return (Path(__file__).parent.parent / "templates" / filename).read_text(encoding="utf-8")
    ref = importlib.resources.files(_PACKAGE).joinpath(filename)
    return ref.read_text(encoding="utf-8")


def load_one_pager_template() -> str:
    """Return the packaged ``one-pager.html`` template body."""
    return _read_template_resource("one-pager.html")


# Per-platform template registries (TAP-7423). Independent literals, like
# CLAUDE_SKILLS/CURSOR_SKILLS (pipeline/platform_skills.py) — nothing enforces
# they match except the dedicated parity test, by design (see that module's
# docstring: a shared-source construction would hide the same drift it exists
# to catch).
CLAUDE_TEMPLATES: dict[str, str] = {
    "one-pager": ONE_PAGER_REL_PATH,
}

CURSOR_TEMPLATES: dict[str, str] = {
    "one-pager": ONE_PAGER_REL_PATH,
}

_TEMPLATE_LOADERS: dict[str, Any] = {
    "one-pager": load_one_pager_template,
}


def _registry_for(platform: str) -> dict[str, str]:
    return CLAUDE_TEMPLATES if platform == "claude" else CURSOR_TEMPLATES


def generate_templates(
    project_root: Path, platform: str, *, dry_run: bool = False
) -> dict[str, Any]:
    """Install or refresh every template registered for *platform*.

    Each entry is a plain overwrite: no managed-block marker, no policy
    header — the file on disk is byte-identical to the packaged template.
    ``overwrite_warnings`` names any path whose on-disk content diverged from
    canonical before it gets replaced, matching
    :func:`tapps_mcp.pipeline.skill_asset_policy.write_companions`'s
    non-delimitable branch.

    Returns ``{"templates": {rel_path: action}, "overwrite_warnings": [...]}``
    where ``action`` is one of ``"created"``, ``"refreshed"``, ``"unchanged"``.
    """
    actions: dict[str, str] = {}
    warnings: list[str] = []
    for name, rel_path in _registry_for(platform).items():
        body = _TEMPLATE_LOADERS[name]()
        target = project_root / rel_path
        if not target.exists():
            action = "created"
        else:
            try:
                current = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                current = None
            if current == body:
                actions[rel_path] = "unchanged"
                continue
            action = "refreshed"
            warning = plan_overwrite_report(target, body)
            if warning:
                warnings.append(warning)
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        actions[rel_path] = action
    return {"templates": actions, "overwrite_warnings": warnings}


def plan_templates(project_root: Path, platform: str) -> dict[str, Any]:
    """Dry-run preview of what :func:`generate_templates` would do, with no writes."""
    return generate_templates(project_root, platform, dry_run=True)


__all__ = [
    "CLAUDE_TEMPLATES",
    "CURSOR_TEMPLATES",
    "ONE_PAGER_REL_PATH",
    "generate_templates",
    "load_one_pager_template",
    "plan_templates",
]
