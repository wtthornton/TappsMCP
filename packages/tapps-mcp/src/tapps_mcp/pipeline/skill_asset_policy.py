"""One place that says how every scaffolded skill file survives ``tapps_upgrade``.

TAP-6497: a skill directory shipped three different upgrade policies and only
one of them was discoverable from inside a file. ``SKILL.md`` carried
``<!-- BEGIN: tapps-skill … -->`` markers and preserved everything outside them;
``assets/prompt-template.md`` and the ``references/*.md`` siblings were
overwritten wholesale on every upgrade; ``learnings.md`` was never overwritten
at all. Nothing in any of those files said which rule applied to it, so a
customization was equally likely to be preserved forever, silently discarded,
or frozen out of every later fix.

The three policies still exist — they are genuinely different needs — but they
are named, documented here, and stamped into each generated file:

``MANAGED_BLOCK``
    The platform body lives between ``BEGIN``/``END`` markers. Upgrade replaces
    only that span; anything a project writes outside the markers survives
    verbatim. Applies to a smart-merge skill's ``SKILL.md``
    (:mod:`tapps_mcp.pipeline.skill_managed_block`) and, since TAP-6497, to
    every marker-delimitable companion asset.

``CREATE_ONLY``
    Project-owned state, written once and never rewritten. ``learnings.md``.

``OVERWRITE``
    Whole-file refresh with no preserved region. Two files land here: a
    non-smart-merge ``SKILL.md`` (``tapps_upgrade`` calls ``generate_skills``
    with ``overwrite=True``, so every one is replaced — only ``tapps_init``
    leaves an existing copy alone), and a companion whose format cannot carry a
    comment marker. For the latter, upgrade **reports** each path whose on-disk
    content differs from canonical before replacing it, so the overwrite is
    never silent (:func:`plan_overwrite_report`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path

Policy = Literal["managed_block", "create_only", "overwrite"]
AssetAction = Literal["created", "refreshed", "migrated", "unchanged"]

ASSET_MARKER_BEGIN_PREFIX = "<!-- BEGIN: tapps-skill-asset"
ASSET_MARKER_END = "<!-- END: tapps-skill-asset -->"

# Heading introducing the preserved region when a pre-marker asset is migrated.
ASSET_PROJECT_REGION_HEADING = (
    "<!-- tapps-skill-asset-project-customizations: preserved from the "
    "pre-marker version — review and trim anything the managed block above now "
    "covers -->"
)

#: One line per policy, rendered into each generated file so the rule that
#: governs it is readable without consulting this module.
POLICY_NOTES: dict[Policy, str] = {
    "managed_block": (
        "upgrade-policy: managed-block. Edits made inside this BEGIN/END block "
        "are regenerated and lost on the next tapps_upgrade — put "
        "project-specific customizations below the END marker instead, where "
        "they survive every upgrade untouched."
    ),
    "create_only": (
        "upgrade-policy: create-only. tapps_upgrade wrote this file once and "
        "never rewrites it. It is project-owned state; edit freely."
    ),
    "overwrite": (
        "upgrade-policy: overwrite. tapps_upgrade replaces this file wholesale "
        "on every run and local edits are lost (tapps_init leaves an existing "
        "copy alone; upgrade does not). Fold the change upstream into the "
        "platform template, or pin the whole directory with an "
        "upgrade_skip_files token."
    ),
}

# Suffixes whose format can carry an HTML comment marker. Anything else falls
# back to ``OVERWRITE`` plus the about-to-overwrite report.
_DELIMITABLE_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown", ".html"})


def is_delimitable(rel_path: str) -> bool:
    """Return whether *rel_path*'s format can hold a managed-block marker."""
    suffix = rel_path[rel_path.rfind(".") :].lower() if "." in rel_path else ""
    return suffix in _DELIMITABLE_SUFFIXES


def policy_for(rel_path: str, *, create_only: bool = False) -> Policy:
    """Return the upgrade policy a companion at *rel_path* gets."""
    if create_only:
        return "create_only"
    return "managed_block" if is_delimitable(rel_path) else "overwrite"


def policy_header(policy: Policy) -> str:
    """Return the in-file HTML-comment header stating *policy*."""
    return f"<!-- {POLICY_NOTES[policy]} -->"


def _asset_marker_begin(skill_name: str, rel_path: str, version: str) -> str:
    return f"{ASSET_MARKER_BEGIN_PREFIX} {skill_name}/{rel_path} v{version} -->"


def asset_block(
    body: str,
    skill_name: str,
    rel_path: str,
    *,
    version: str = __version__,
) -> str:
    """Return *body* delimited by the asset BEGIN/END markers, header excluded."""
    begin = _asset_marker_begin(skill_name, rel_path, version)
    return f"{begin}\n{body.strip('\n')}\n{ASSET_MARKER_END}"


def wrap_asset(
    body: str,
    skill_name: str,
    rel_path: str,
    *,
    version: str = __version__,
) -> str:
    """Return the full scaffolded file: policy header + managed block."""
    block = asset_block(body, skill_name, rel_path, version=version)
    return f"{policy_header('managed_block')}\n{block}\n"


def _find_asset_block(content: str) -> tuple[int, int] | None:
    begin = content.find(ASSET_MARKER_BEGIN_PREFIX)
    if begin == -1:
        return None
    end_idx = content.find(ASSET_MARKER_END, begin)
    if end_idx == -1:
        return None
    return begin, end_idx + len(ASSET_MARKER_END)


def strip_asset_scaffolding(content: str) -> str:
    """Return *content* with the policy header and asset markers removed.

    Used to compare a scaffolded asset against canonical text — a doctor check
    or an overwrite decision cares about the body, not the wrapper.
    """
    span = _find_asset_block(content)
    if span is None:
        return content
    begin, end = span
    inner_start = content.find("-->", begin) + len("-->")
    inner = content[inner_start : end - len(ASSET_MARKER_END)]
    return inner.strip("\n")


def has_asset_customization(content: str) -> bool:
    """Return whether text outside the managed block is non-trivial.

    The policy header is scaffolding, not customization, so it is excluded. A
    file with no markers at all counts as uncustomized here — callers decide
    separately whether such a file drifted from canonical.
    """
    span = _find_asset_block(content)
    if span is None:
        return False
    begin, end = span
    outside = (content[:begin] + content[end:]).replace(policy_header("managed_block"), "")
    return bool(outside.strip())


def install_or_refresh_asset(
    path: Path,
    body: str,
    skill_name: str,
    rel_path: str,
    *,
    dry_run: bool = False,
    version: str = __version__,
) -> AssetAction:
    """Install or surgically refresh a marker-delimited companion asset.

    - **File missing** → write header + markered block (``"created"``).
    - **Markers present** → replace the block if it differs (``"refreshed"``),
      else ``"unchanged"``. Text outside the markers is preserved verbatim.
    - **Markers absent** (a copy scaffolded before TAP-6497, possibly edited) →
      write the fresh block and keep the prior body below it as a preserved
      project region (``"migrated"``). Nothing is lost; the operator trims the
      duplicate. An unmodified pre-marker copy is *not* preserved — it is
      byte-identical to canonical and would only add noise.
    """
    header = policy_header("managed_block")
    block = asset_block(body, skill_name, rel_path, version=version)
    fresh = f"{header}\n{block}\n"

    if not path.exists():
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fresh, encoding="utf-8")
        return "created"

    original = path.read_text(encoding="utf-8")
    span = _find_asset_block(original)

    if span is not None:
        begin, end = span
        # Project content above the block, minus the header the platform owns.
        head = original[:begin].replace(header, "").lstrip("\n")
        updated = f"{header}\n{head}{block}{original[end:]}"
        if updated == original:
            return "unchanged"
        action: AssetAction = "refreshed"
    elif original.strip("\n") == body.strip("\n"):
        # Pristine pre-marker copy: adopt markers, preserve nothing.
        updated = fresh
        action = "refreshed"
    else:
        preserved = original.strip("\n")
        updated = f"{fresh}\n{ASSET_PROJECT_REGION_HEADING}\n\n{preserved}\n"
        action = "migrated"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action


def create_only_body(body: str) -> str:
    """Return *body* prefixed with the create-only policy header."""
    return f"{policy_header('create_only')}\n{body.lstrip('\n')}"


def plan_overwrite_report(path: Path, body: str) -> str | None:
    """Return a warning line when a non-delimitable asset would lose edits.

    Returns ``None`` when the file is absent or already matches canonical —
    there is nothing to report. TAP-6497 acceptance item 2: a whole-file
    overwrite of customized content must be named before it happens.
    """
    if not path.exists():
        return None
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    expected = f"{policy_header('overwrite')}\n{body.lstrip('\n')}"
    if current in (expected, body):
        return None
    return (
        f"{path} was customized but its format carries no managed-block marker "
        f"— tapps_upgrade overwrites it wholesale. Copy anything you need out "
        f"first, then fold the change upstream into the platform template."
    )


def write_companions(
    skill_dir: Path,
    skill_name: str,
    companions: dict[str, str],
    create_only: dict[str, str],
) -> dict[str, Any]:
    """Write one skill's companion files, each under the policy it declares.

    ``companions`` get a managed block when their format can hold a marker, so
    project text outside the markers survives every upgrade; the rest are
    overwritten wholesale and each customized path is named in
    ``overwrite_warnings`` first. ``create_only`` entries are written solely
    when absent.

    Returns ``{"assets": {rel_path: action}, "overwrite_warnings": [...]}``.
    """
    actions: dict[str, str] = {}
    warnings: list[str] = []

    for rel_path, content in companions.items():
        target = skill_dir / rel_path
        if is_delimitable(rel_path):
            actions[rel_path] = install_or_refresh_asset(target, content, skill_name, rel_path)
            continue
        warning = plan_overwrite_report(target, content)
        if warning:
            warnings.append(warning)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{policy_header('overwrite')}\n{content.lstrip('\n')}", encoding="utf-8")
        actions[rel_path] = "overwritten"

    for rel_path, content in create_only.items():
        target = skill_dir / rel_path
        if target.exists():
            actions[rel_path] = "preserved (create-only)"
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(create_only_body(content), encoding="utf-8")
        actions[rel_path] = "created"

    return {"assets": actions, "overwrite_warnings": warnings}


__all__ = [
    "ASSET_MARKER_BEGIN_PREFIX",
    "ASSET_MARKER_END",
    "ASSET_PROJECT_REGION_HEADING",
    "POLICY_NOTES",
    "AssetAction",
    "Policy",
    "asset_block",
    "create_only_body",
    "has_asset_customization",
    "install_or_refresh_asset",
    "is_delimitable",
    "plan_overwrite_report",
    "policy_for",
    "policy_header",
    "strip_asset_scaffolding",
    "wrap_asset",
    "write_companions",
]
