"""Plugin package builder for Claude Code marketplace distribution.

Thin facade over
:func:`tapps_mcp.pipeline.platform_bundles.generate_claude_plugin_bundle` so
that `tapps-mcp build-plugin` (this class) and a direct call to
``generate_claude_plugin_bundle()`` emit byte-identical trees from one
implementation.

Before this unification, ``PluginBuilder`` had its own independent bundling
logic that had drifted from ``generate_claude_plugin_bundle`` and was never
exercised as a real, installable plugin: it wrote namespaced
``skills/tapps-mcp-<name>/`` directories (not matching the documented
``skills/<skill-id>/SKILL.md`` layout), a Cursor-shaped
``rules/python-quality.md`` prose file, a ``settings.json`` permissions stub
that plugin bundles do not support, and a ``hooks/hooks.json`` whose commands
pointed at ``.claude/hooks/<script>.sh`` — paths that only exist for a
per-project ``tapps-mcp init`` install, never inside the bundle itself, which
it also never wrote. A plugin built from that path would have every hook
404 at invocation time. That implementation is retired.

``engagement_level`` (still accepted here for CLI/API compatibility) now
flows into ``plugin.json``'s ``userConfig.engagement_level.default`` instead
of prose, since that is the field Claude Code actually reads for
user-configurable defaults.

Usage::

    tapps-mcp build-plugin --output-dir ./tapps-mcp-plugin/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.common.logging import get_logger
from tapps_mcp import __version__

log = get_logger(__name__)


@dataclass
class PluginBuilder:
    """Build a Claude Code plugin directory by delegating to
    ``generate_claude_plugin_bundle`` (see module docstring for why)."""

    output_dir: Path
    engagement_level: str = "medium"
    _result: dict[str, Any] = field(default_factory=dict)

    def build(self) -> Path:
        """Generate the complete plugin directory. Returns the output path."""
        from tapps_mcp.pipeline.platform_bundles import generate_claude_plugin_bundle

        self.output_dir.mkdir(parents=True, exist_ok=True)
        gen_result = generate_claude_plugin_bundle(
            self.output_dir,
            version=__version__,
            engagement_level_default=self.engagement_level,
        )
        self._result = {
            "files_created": gen_result["files_created"],
            "output_dir": str(self.output_dir),
            "version": __version__,
        }
        log.info("plugin_built", output_dir=str(self.output_dir))
        return self.output_dir

    @property
    def result(self) -> dict[str, Any]:
        """Build result metadata."""
        return self._result
