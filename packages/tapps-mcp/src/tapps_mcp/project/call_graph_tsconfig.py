"""tsconfig ``compilerOptions.paths`` alias resolution for TS call graphs (TAP-4540).

S4 of the call-graph language expansion. Reads ``tsconfig.json`` from the
project root and turns a path-alias specifier (``@/util``) into a slash-delimited
module name matching the ``_ts_file_to_module`` convention (leading ``src/``
stripped, ``.ts``/``.tsx`` suffix dropped).

Deterministic contract (ADR-0004): no LLM, no network. A missing / malformed
config, or a specifier that matches no alias, yields ``None`` — the caller keeps
the ``path_alias_unresolved`` gap rather than guessing a target.

Scope kept deliberately small: the common ``{"@/*": ["src/*"]}`` wildcard form
plus exact (non-wildcard) aliases. ``extends``, JSON5 comments/trailing commas,
and project references are out of scope — a config we cannot parse cleanly
degrades to "no aliases" (empty map), never a crash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TsconfigPaths:
    """Resolved ``compilerOptions.paths`` + ``baseUrl`` from a project ``tsconfig``.

    ``base_url`` is the directory (relative to the project root) that ``paths``
    targets are resolved against; defaults to ``.`` (the project root) per the
    TypeScript spec when ``paths`` is present but ``baseUrl`` is not.
    """

    base_url: str = "."
    # Alias pattern -> list of substitution targets. A wildcard alias ends with
    # ``/*`` and its targets contain a single ``*``. Exact aliases have neither.
    aliases: dict[str, list[str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.aliases


def load_tsconfig_paths(project_root: Path) -> TsconfigPaths:
    """Load ``compilerOptions.paths`` / ``baseUrl`` from ``<root>/tsconfig.json``.

    Returns an empty ``TsconfigPaths`` (no aliases) when the file is absent,
    unreadable, not valid JSON, or has no ``paths`` block — the caller treats an
    empty config as "cannot resolve, keep the gap".
    """
    path = project_root / "tsconfig.json"
    if not path.is_file():
        return TsconfigPaths()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        # Malformed / commented tsconfig — degrade to no aliases, never crash.
        return TsconfigPaths()
    if not isinstance(raw, dict):
        return TsconfigPaths()
    compiler = raw.get("compilerOptions")
    if not isinstance(compiler, dict):
        return TsconfigPaths()
    paths_raw = compiler.get("paths")
    if not isinstance(paths_raw, dict):
        return TsconfigPaths()

    base_url = compiler.get("baseUrl")
    base = base_url if isinstance(base_url, str) and base_url.strip() else "."

    aliases: dict[str, list[str]] = {}
    for alias, targets in paths_raw.items():
        if not isinstance(alias, str) or not isinstance(targets, list):
            continue
        target_list = [t for t in targets if isinstance(t, str) and t.strip()]
        if target_list:
            aliases[alias] = target_list
    return TsconfigPaths(base_url=base, aliases=aliases)


def resolve_path_alias(config: TsconfigPaths, specifier: str) -> str | None:
    """Resolve an alias ``specifier`` to a module name, or ``None`` if no match.

    Handles the two ``paths`` forms:

    * **Wildcard** (``"@/*": ["src/*"]``): the ``*`` captures the tail of the
      specifier and substitutes it into the target's ``*``.
    * **Exact** (``"@app": ["src/app/index"]``): the whole specifier must equal
      the alias key; the first target is used verbatim.

    The resolved filesystem-style target (``baseUrl`` + substituted target) is
    normalized to the ``_ts_file_to_module`` convention: leading ``src/``
    stripped, any ``.ts``/``.tsx``/``.js``/``.jsx`` suffix dropped. Returns
    ``None`` when nothing matches so the caller keeps the honest gap.
    """
    if config.is_empty():
        return None
    # Deterministic order: try the longest alias prefix first so a specific
    # alias wins over a broad one. Exact matches are handled inside the loop.
    for alias in sorted(config.aliases, key=len, reverse=True):
        targets = config.aliases[alias]
        substituted = _match_alias(alias, targets, specifier)
        if substituted is not None:
            return _target_to_module(config.base_url, substituted)
    return None


def _match_alias(alias: str, targets: list[str], specifier: str) -> str | None:
    """Return the substituted target path for ``specifier`` under ``alias``.

    Only the first target is consulted (the common single-target form); multiple
    fallback targets would need on-disk existence checks to disambiguate, which
    is out of scope for the deterministic contract.
    """
    if alias.endswith("/*"):
        prefix = alias[:-1]  # keep the trailing slash, drop the star.
        if not specifier.startswith(prefix):
            return None
        tail = specifier[len(prefix) :]
        target = targets[0]
        if "*" not in target:
            return None
        return target.replace("*", tail, 1)
    # Exact alias: the specifier must equal the key exactly.
    if specifier == alias:
        return targets[0]
    return None


def _target_to_module(base_url: str, target: str) -> str:
    """Normalize a ``baseUrl``-relative target path to a module name."""
    combined = target if base_url in {".", ""} else f"{base_url.rstrip('/')}/{target}"
    # Drop a recognized TS/JS suffix.
    for suffix in (".tsx", ".ts", ".jsx", ".js"):
        if combined.endswith(suffix):
            combined = combined[: -len(suffix)]
            break
    parts = [p for p in combined.split("/") if p not in {"", "."}]
    # Monorepo: packages/<pkg>/src/... — match _ts_file_to_module.
    if len(parts) >= 3 and parts[0] == "packages" and parts[2] == "src":
        parts = parts[3:]
    elif parts and parts[0] == "src":
        parts = parts[1:]
    return "/".join(parts)
