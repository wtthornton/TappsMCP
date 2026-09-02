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
    Whole-file refresh with no preserved region. Applies to a companion whose
    format cannot carry a comment marker — upgrade **reports** each path whose
    on-disk content differs from canonical before replacing it, so the
    overwrite is never silent (:func:`plan_overwrite_report`). Every
    ``SKILL.md`` — smart-merge or not — instead carries a managed block since
    TAP-6948 s3 (:mod:`tapps_mcp.pipeline.skill_managed_block`); there is no
    longer a wholesale-overwritten ``SKILL.md``.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path

Policy = Literal["managed_block", "create_only", "overwrite"]
AssetAction = Literal["created", "refreshed", "migrated", "unchanged"]


class _Syntax(NamedTuple):
    """A comment style: the token that opens a line/block, and the one that closes it.

    ``close`` is ``""`` for a line-comment style (``#``, ``//``) — the marker is
    a single line with no closing token, ending at the newline instead.
    """

    open: str
    close: str


def _marker_begin_prefix(syntax: _Syntax) -> str:
    return f"{syntax.open} BEGIN: tapps-skill-asset"


def _marker_end(syntax: _Syntax) -> str:
    if syntax.close:
        return f"{syntax.open} END: tapps-skill-asset {syntax.close}"
    return f"{syntax.open} END: tapps-skill-asset"


# The three comment styles a scaffolded asset can carry. Every delimitable
# suffix maps to exactly one of these; adding a suffix means picking one of
# these (or defining a new one), never inventing an ad hoc marker shape.
_HTML_SYNTAX = _Syntax("<!--", "-->")
_HASH_SYNTAX = _Syntax("#", "")
_SLASH_SYNTAX = _Syntax("//", "")
_ALL_SYNTAXES: tuple[_Syntax, ...] = (_HTML_SYNTAX, _HASH_SYNTAX, _SLASH_SYNTAX)

# Derived from _HTML_SYNTAX rather than duplicated as literals, so the
# pre-TAP-6884 html marker shape can never drift from what wrap_asset/
# asset_block actually emit for a .md/.markdown/.html asset.
ASSET_MARKER_BEGIN_PREFIX = _marker_begin_prefix(_HTML_SYNTAX)
ASSET_MARKER_END = _marker_end(_HTML_SYNTAX)

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

# Suffixes whose format can carry a comment marker, and which comment style
# each one uses. Anything else falls back to ``OVERWRITE`` plus the
# about-to-overwrite report. ``.sh``/``.py`` share the hash style; ``.js``
# gets slash; the original three share the html style unchanged.
_COMMENT_SYNTAX: dict[str, _Syntax] = {
    ".md": _HTML_SYNTAX,
    ".markdown": _HTML_SYNTAX,
    ".html": _HTML_SYNTAX,
    ".sh": _HASH_SYNTAX,
    ".py": _HASH_SYNTAX,
    ".js": _SLASH_SYNTAX,
}
_DELIMITABLE_SUFFIXES: frozenset[str] = frozenset(_COMMENT_SYNTAX)


def _syntax_for(rel_path: str) -> _Syntax:
    suffix = rel_path[rel_path.rfind(".") :].lower() if "." in rel_path else ""
    return _COMMENT_SYNTAX.get(suffix, _HTML_SYNTAX)


def is_delimitable(rel_path: str) -> bool:
    """Return whether *rel_path*'s format can hold a managed-block marker."""
    suffix = rel_path[rel_path.rfind(".") :].lower() if "." in rel_path else ""
    return suffix in _DELIMITABLE_SUFFIXES


def policy_for(rel_path: str, *, create_only: bool = False) -> Policy:
    """Return the upgrade policy a companion at *rel_path* gets."""
    if create_only:
        return "create_only"
    return "managed_block" if is_delimitable(rel_path) else "overwrite"


def _header_text(policy: Policy, syntax: _Syntax) -> str:
    note = POLICY_NOTES[policy]
    if syntax.close:
        return f"{syntax.open} {note} {syntax.close}"
    return f"{syntax.open} {note}"


def policy_header(policy: Policy, rel_path: str = "") -> str:
    """Return the in-file comment header stating *policy*, in *rel_path*'s syntax.

    *rel_path* defaults to ``""``, which resolves to the original html-comment
    style — every existing caller that omits it keeps today's output exactly.
    """
    return _header_text(policy, _syntax_for(rel_path))


def _split_shebang(body: str) -> tuple[str, str]:
    """Split a leading ``#!`` line (with its newline) off *body*, if present.

    The kernel only honors a shebang on line 1, so callers lift it ahead of
    the policy header instead of leaving it inside the managed block.
    """
    if not body.startswith("#!"):
        return "", body
    newline_idx = body.find("\n")
    if newline_idx == -1:
        return f"{body}\n", ""
    return body[: newline_idx + 1], body[newline_idx + 1 :]


def _asset_marker_begin(skill_name: str, rel_path: str, version: str) -> str:
    syntax = _syntax_for(rel_path)
    prefix = _marker_begin_prefix(syntax)
    close = f" {syntax.close}" if syntax.close else ""
    return f"{prefix} {skill_name}/{rel_path} v{version}{close}"


def asset_block(
    body: str,
    skill_name: str,
    rel_path: str,
    *,
    version: str = __version__,
) -> str:
    """Return *body* delimited by the asset BEGIN/END markers, header excluded."""
    begin = _asset_marker_begin(skill_name, rel_path, version)
    end = _marker_end(_syntax_for(rel_path))
    return f"{begin}\n{body.strip('\n')}\n{end}"


def wrap_asset(
    body: str,
    skill_name: str,
    rel_path: str,
    *,
    version: str = __version__,
) -> str:
    """Return the full scaffolded file: policy header + managed block.

    When *body* starts with a ``#!`` shebang, it is kept on line 1 of the
    file — the policy header and marker block follow after it — so a
    scaffolded script with its executable bit set can still run directly
    (TAP-6903).
    """
    shebang, rest = _split_shebang(body)
    block = asset_block(rest, skill_name, rel_path, version=version)
    return f"{shebang}{policy_header('managed_block', rel_path)}\n{block}\n"


class _AssetSpan(NamedTuple):
    begin: int
    end: int
    inner_start: int
    syntax: _Syntax


def _find_asset_block(content: str) -> _AssetSpan | None:
    """Locate the marker span in *content*, detecting its comment syntax.

    The syntax is read off the content itself (already-scaffolded text is
    self-describing) rather than passed in, so this and its callers stay
    usable from just a file's text. Stops hardcoding ``-->``: the inner-body
    start is computed from whichever syntax's begin marker actually matched.
    """
    for syntax in _ALL_SYNTAXES:
        prefix = _marker_begin_prefix(syntax)
        begin = content.find(prefix)
        if begin == -1:
            continue
        end_marker = _marker_end(syntax)
        end_idx = content.find(end_marker, begin)
        if end_idx == -1:
            continue
        if syntax.close:
            inner_start = content.find(syntax.close, begin) + len(syntax.close)
        else:
            inner_start = content.find("\n", begin) + 1
        return _AssetSpan(begin, end_idx + len(end_marker), inner_start, syntax)
    return None


def strip_asset_scaffolding(content: str) -> str:
    """Return *content* with the policy header and asset markers removed.

    Used to compare a scaffolded asset against canonical text — a doctor check
    or an overwrite decision cares about the body, not the wrapper.
    """
    span = _find_asset_block(content)
    if span is None:
        return content
    inner = content[span.inner_start : span.end - len(_marker_end(span.syntax))]
    body = inner.strip("\n")
    shebang, _ = _split_shebang(content)
    return f"{shebang}{body}"


def has_asset_customization(content: str) -> bool:
    """Return whether text outside the managed block is non-trivial.

    The policy header is scaffolding, not customization, so it is excluded. A
    file with no markers at all counts as uncustomized here — callers decide
    separately whether such a file drifted from canonical.
    """
    span = _find_asset_block(content)
    if span is None:
        return False
    header = _header_text("managed_block", span.syntax)
    outside = (content[: span.begin] + content[span.end :]).replace(header, "")
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
    shebang, rest = _split_shebang(body)
    header = policy_header("managed_block", rel_path)
    block = asset_block(rest, skill_name, rel_path, version=version)
    prefix = f"{shebang}{header}\n"
    fresh = f"{prefix}{block}\n"

    if not path.exists():
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fresh, encoding="utf-8")
        return "created"

    original = path.read_text(encoding="utf-8")
    span = _find_asset_block(original)

    if span is not None:
        begin, end = span.begin, span.end
        # Project content above the block, minus the shebang + header the
        # platform owns.
        before = original[:begin]
        if before.startswith(prefix):
            head = before[len(prefix) :]
        else:
            head = before.replace(header, "").lstrip("\n")
        updated = f"{prefix}{head}{block}{original[end:]}"
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


def write_project_script(
    project_root: Path,
    rel_path: str,
    body: str,
    skill_name: str,
    *,
    dry_run: bool = False,
    version: str = __version__,
) -> AssetAction:
    """Install or refresh an executable script at a project-root-relative path.

    Unlike :func:`write_companions` (skill-dir scoped, under
    ``.claude/skills/<name>/``), this targets a different destination —
    typically ``scripts/<name>`` at the project root — for the executable
    asset class (TAP-6884). Same managed-block refresh semantics as any other
    delimitable asset via :func:`install_or_refresh_asset`; the only addition
    is setting the executable bit, following the chmod idiom already used at
    ``github_governance.generate_ruleset_scripts`` and
    ``platform_bundles.generate_agent_teams_hooks``.
    """
    target = project_root / rel_path
    action = install_or_refresh_asset(
        target, body, skill_name, rel_path, dry_run=dry_run, version=version
    )
    if not dry_run:
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
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
    "write_project_script",
]
