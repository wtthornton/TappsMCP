"""TappsPlatform — combined MCP server composition layer.

Composes TappsMCP (code quality) and DocsMCP (documentation) into a unified
MCP server with graceful degradation when optional packages are missing.
"""

from __future__ import annotations
