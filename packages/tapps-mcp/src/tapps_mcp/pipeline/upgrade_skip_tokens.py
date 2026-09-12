"""Backward-compatible re-export of the ``upgrade_skip_files`` vocabulary.

The vocabulary lives in :mod:`tapps_core.config.upgrade_skip_tokens` (TAP-7429):
tapps-core is the base package (178 tapps-mcp files import it, zero tapps-core
files import tapps-mcp), and :mod:`tapps_core.config.settings` needs the same
table to render its ``Field(description=...)`` sentence from live data instead
of hand-restated prose. This module re-exports it unchanged so existing
importers (:mod:`tapps_mcp.pipeline.upgrade`,
:mod:`tapps_mcp.distribution.doctor_platform`, and their tests) need no path
changes.
"""

from __future__ import annotations

from tapps_core.config.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    SKIP_TOKENS,
    applied_skip_tokens,
    describe_unknown_skip_token,
    describe_unknown_skip_tokens,
    nearest_token,
    unknown_skip_tokens,
)

__all__ = [
    "ALL_SKIP_TOKENS",
    "SKIP_TOKENS",
    "applied_skip_tokens",
    "describe_unknown_skip_token",
    "describe_unknown_skip_tokens",
    "nearest_token",
    "unknown_skip_tokens",
]
