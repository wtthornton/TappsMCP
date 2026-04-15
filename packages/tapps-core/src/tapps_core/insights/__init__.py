"""tapps_core.insights — shared insight schema for cross-server knowledge exchange.

This module provides the canonical InsightEntry type used by both tapps-mcp and
docs-mcp to write structured, typed, versioned knowledge into tapps-brain.

Quick start::

    from tapps_core.insights import InsightEntry, InsightType, InsightOrigin
    from tapps_core.insights import migrate_memory_entry_to_insight, bulk_migrate
    from tapps_core.insights import InsightClient, enforce_scope
    from tapps_core.insights import annotate_provenance, format_provenance_summary

Public API
----------
Models:
    InsightEntry          — versioned MemoryEntry subclass
    InsightType           — quality | architecture | documentation | security | pattern | dependency
    InsightOrigin         — tapps-mcp | docs-mcp | user | unknown
    SubjectKind           — file | module | class | function | system
    INSIGHT_SCHEMA_VERSION — int sentinel (currently 1)

Migration:
    migrate_memory_entry_to_insight  — promote a single MemoryEntry
    bulk_migrate                     — promote a list; returns InsightMigrationResult
    InsightMigrationResult           — result dataclass with counts and failed_keys

Client (STORY-102.4):
    InsightClient         — write/search/promote InsightEntry via tapps-brain

Scope enforcement (STORY-102.5):
    enforce_scope         — clamp InsightEntry scope, raise ScopeViolation on error
    validate_origin_scope — non-mutating audit warnings
    ScopeViolation        — raised by enforce_scope on unresolvable violation

Provenance (STORY-102.6):
    ProvenanceAnnotation       — structured provenance metadata model
    annotate_provenance        — attach _provenance to serialised entries
    format_provenance_summary  — human-readable recall provenance block
"""

from __future__ import annotations

from tapps_core.insights.client import InsightClient as InsightClient
from tapps_core.insights.migration import (
    InsightMigrationResult as InsightMigrationResult,
)
from tapps_core.insights.migration import (
    bulk_migrate as bulk_migrate,
)
from tapps_core.insights.migration import (
    migrate_memory_entry_to_insight as migrate_memory_entry_to_insight,
)
from tapps_core.insights.models import INSIGHT_SCHEMA_VERSION as INSIGHT_SCHEMA_VERSION
from tapps_core.insights.models import InsightEntry as InsightEntry
from tapps_core.insights.models import InsightOrigin as InsightOrigin
from tapps_core.insights.models import InsightType as InsightType
from tapps_core.insights.models import SubjectKind as SubjectKind
from tapps_core.insights.provenance import (
    ProvenanceAnnotation as ProvenanceAnnotation,
)
from tapps_core.insights.provenance import (
    annotate_provenance as annotate_provenance,
)
from tapps_core.insights.provenance import (
    format_provenance_summary as format_provenance_summary,
)
from tapps_core.insights.scope import ScopeViolation as ScopeViolation
from tapps_core.insights.scope import enforce_scope as enforce_scope
from tapps_core.insights.scope import (
    validate_origin_scope as validate_origin_scope,
)

__all__ = [
    "INSIGHT_SCHEMA_VERSION",
    "InsightClient",
    "InsightEntry",
    "InsightMigrationResult",
    "InsightOrigin",
    "InsightType",
    "ProvenanceAnnotation",
    "ScopeViolation",
    "SubjectKind",
    "annotate_provenance",
    "bulk_migrate",
    "enforce_scope",
    "format_provenance_summary",
    "migrate_memory_entry_to_insight",
    "validate_origin_scope",
]
