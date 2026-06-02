"""Tests for deterministic KG entity-key derivation (TAP-1949)."""

from __future__ import annotations

import uuid

import pytest

from tapps_core.knowledge.kg_keys import KG_NAMESPACE, entity_uuid


def test_returns_uuid() -> None:
    result = entity_uuid("tapps-mcp", "module", "tapps_core.brain_bridge")
    assert isinstance(result, uuid.UUID)
    assert result.version == 5


def test_deterministic_same_input() -> None:
    """The same triple always maps to the same UUID."""
    a = entity_uuid("tapps-mcp", "module", "tapps_core.brain_bridge")
    b = entity_uuid("tapps-mcp", "module", "tapps_core.brain_bridge")
    assert a == b


def test_distinct_components_distinct_ids() -> None:
    """Varying any one component yields a different UUID."""
    base = entity_uuid("tapps-mcp", "module", "pkg.mod")
    assert entity_uuid("other-proj", "module", "pkg.mod") != base
    assert entity_uuid("tapps-mcp", "package", "pkg.mod") != base
    assert entity_uuid("tapps-mcp", "module", "pkg.other") != base


def test_matches_documented_derivation() -> None:
    """Derivation equals uuid5(KG_NAMESPACE, 'project|type|name')."""
    expected = uuid.uuid5(KG_NAMESPACE, "tapps-mcp|symbol|tapps_core.foo.bar")
    assert entity_uuid("tapps-mcp", "symbol", "tapps_core.foo.bar") == expected


def test_namespace_is_pinned() -> None:
    """Guard against accidental namespace change (would orphan all IDs)."""
    assert KG_NAMESPACE == uuid.NAMESPACE_OID


def test_property_injective_over_realistic_inputs() -> None:
    """10,000 distinct realistic triples map to 10,000 distinct UUIDs.

    Inputs mimic the real domain: slug project ids, the closed entity-type
    vocabulary, and dotted-identifier / POSIX-path canonical names (none of
    which contain the ``|`` separator).
    """
    types = ("package", "module", "symbol", "doc")
    triples: set[tuple[str, str, str]] = set()
    i = 0
    while len(triples) < 10_000:
        project = f"proj-{i % 7}"
        etype = types[i % len(types)]
        name = f"pkg{i % 13}.mod{i % 31}.sym{i}"
        triples.add((project, etype, name))
        i += 1

    ids = {entity_uuid(p, t, n) for p, t, n in triples}
    assert len(ids) == len(triples)


@pytest.mark.parametrize(
    ("project", "etype", "name"),
    [
        ("tapps-mcp", "package", "tapps_core"),
        ("tapps-mcp", "module", "tapps_core.knowledge.kg_keys"),
        ("tapps-mcp", "symbol", "tapps_core.knowledge.kg_keys.entity_uuid"),
        ("tapps-mcp", "doc", "docs/ARCHITECTURE.md"),
    ],
)
def test_stable_across_calls(project: str, etype: str, name: str) -> None:
    assert entity_uuid(project, etype, name) == entity_uuid(project, etype, name)
