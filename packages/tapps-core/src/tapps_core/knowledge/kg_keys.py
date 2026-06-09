"""Deterministic UUIDv5 key derivation for Knowledge-Graph entities.

Centralises entity-ID derivation so that re-running a KG writer (docs-mcp's
``brain_writer`` refactor in TAP-1948, ``tapps_quality_gate``'s event recorder
in TAP-2003, or any future writer) produces the *same* entity UUID for the
same logical entity. That is what makes :meth:`BrainBridge.upsert_entity`
truly idempotent and keeps the ``kg_entities`` table from growing unboundedly
on every regeneration.

The derivation is::

    uuid.uuid5(KG_NAMESPACE, f"{project_id}|{entity_type}|{canonical_name}")

.. warning::
   :data:`KG_NAMESPACE` is load-bearing and MUST NOT change. Changing it
   re-derives every entity UUID, orphaning all existing ``kg_entities`` /
   ``kg_edges`` / ``kg_evidence`` rows in the brain. Treat it as immutable.
"""

from __future__ import annotations

import uuid

__all__ = ["KEY_SEPARATOR", "KG_NAMESPACE", "entity_spec", "entity_uuid"]

# Immutable namespace root for all KG entity-ID derivation. DO NOT CHANGE —
# see the module docstring. The stdlib OID namespace is the stable root per
# TAP-1949 ("UUIDv5 over a namespace is the canonical Python-stdlib approach").
KG_NAMESPACE: uuid.UUID = uuid.NAMESPACE_OID

# Field separator for the canonical key string. Entity types are a closed
# vocabulary (package/module/symbol/doc) and canonical names are dotted
# identifiers or POSIX paths, so this character never appears within a
# component — keeping the join injective over the valid input domain.
KEY_SEPARATOR = "|"


def entity_spec(entity_type: str, canonical_name: str) -> dict[str, str]:
    """Build a brain ``EntitySpec`` dict for :meth:`BrainBridge.record_kg_event`.

    Args:
        entity_type: Closed-vocabulary entity kind (e.g. ``"file"``, ``"tool"``).
        canonical_name: Stable identity within the type (path, tool name, rule id).
    """
    return {"entity_type": entity_type, "canonical_name": canonical_name}


def entity_uuid(project_id: str, entity_type: str, canonical_name: str) -> uuid.UUID:
    """Return the deterministic UUIDv5 for a KG entity.

    The same ``(project_id, entity_type, canonical_name)`` triple always maps
    to the same UUID, so repeated upserts of the same entity collapse to one
    ``kg_entities`` row.

    Args:
        project_id: Brain project slug (e.g. ``"tapps-mcp"``).
        entity_type: Closed-vocabulary entity kind — ``"package"``,
            ``"module"``, ``"symbol"``, or ``"doc"``. Must not contain the
            :data:`KEY_SEPARATOR`.
        canonical_name: Stable identity within the type — a dotted module
            path, qualified symbol name, or POSIX doc path. Must not contain
            the :data:`KEY_SEPARATOR`.

    Returns:
        The derived :class:`uuid.UUID`.
    """
    key = KEY_SEPARATOR.join((project_id, entity_type, canonical_name))
    return uuid.uuid5(KG_NAMESPACE, key)
