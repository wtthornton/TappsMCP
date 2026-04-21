"""Linear SDLC module (TAP-410).

Portable, parameterized templates for the Linear Software Development Life
Cycle workflow. ``tapps_init`` deploys the rendered output into consuming
projects; ``tapps_upgrade`` refreshes it.

Templates are parameterized by :class:`LinearSDLCConfig` — the issue prefix
(e.g. ``TAP``), agent name, and Linear skill install path — so the same
module works across every project using the workflow.

Public surface:

* :class:`LinearSDLCConfig` — render config
* :func:`render_all` — returns ``{relative_path: rendered_content}``
* :data:`TEMPLATE_PATHS` — ordered list of relative paths produced
"""

from __future__ import annotations

from tapps_mcp.pipeline.linear_sdlc.config import LinearSDLCConfig
from tapps_mcp.pipeline.linear_sdlc.renderer import (
    TEMPLATE_PATHS,
    render_all,
    render_template,
)

__all__ = [
    "TEMPLATE_PATHS",
    "LinearSDLCConfig",
    "render_all",
    "render_template",
]
