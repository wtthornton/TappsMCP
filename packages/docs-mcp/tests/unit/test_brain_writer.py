"""Tests for docs_mcp.integrations.brain_writer (STORY-102.2, TAP-1919).

Strategy: the BrainBridge factory is patched out with a lightweight
FakeBridge so tests run without a live tapps-brain (HTTP or in-process)
and without resolving the bridge transport. The FakeBridge captures every
save() call — including kwargs — for assertion. Tests are async because
the writer now routes through ``bridge.save()`` which is async on both
:class:`BrainBridge` and :class:`HttpBrainBridge`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from docs_mcp.integrations.brain_writer import (
    ArchitectureBrainWriter,
    BrainWriteResult,
    _build_key,
    _slugify,
    _truncate,
)

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class FakeBridge:
    """Minimal stand-in for tapps_core.brain_bridge.BrainBridge."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def save(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"key": kwargs["key"]}


def _make_arch_result(
    package_count: int = 3,
    module_count: int = 12,
    edge_count: int = 20,
    class_count: int = 8,
) -> Any:
    """Build a minimal ArchitectureResult-like object."""
    r = MagicMock()
    r.package_count = package_count
    r.module_count = module_count
    r.edge_count = edge_count
    r.class_count = class_count
    r.format = "html"
    return r


def _make_module_node(
    name: str = "mypackage",
    path: str = "src/mypackage",
    is_package: bool = True,
    public_api_count: int = 5,
    function_count: int = 3,
    class_count: int = 2,
    module_docstring: str | None = None,
    submodules: list[Any] | None = None,
) -> MagicMock:
    node = MagicMock()
    node.name = name
    node.path = path
    node.is_package = is_package
    node.public_api_count = public_api_count
    node.function_count = function_count
    node.class_count = class_count
    node.module_docstring = module_docstring
    node.submodules = submodules or []
    return node


def _make_module_map(
    project_name: str = "myproject",
    nodes: list[Any] | None = None,
    entry_points: list[str] | None = None,
) -> MagicMock:
    mm = MagicMock()
    mm.project_name = project_name
    mm.module_tree = [_make_module_node()] if nodes is None else nodes
    mm.entry_points = [] if entry_points is None else entry_points
    return mm


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_lowercase(self):
        assert _slugify("MyPackage") == "mypackage"

    def test_spaces_become_dots(self):
        assert _slugify("my package") == "my.package"

    def test_underscore_preserved(self):
        assert _slugify("my_package") == "my_package"

    def test_dash_preserved(self):
        assert _slugify("my-package") == "my-package"

    def test_invalid_chars_replaced(self):
        assert _slugify("my@pack!age") == "my.pack.age"

    def test_collapses_runs(self):
        assert _slugify("my  package") == "my.package"

    def test_empty_string_returns_unknown(self):
        assert _slugify("") == "unknown"

    def test_strips_leading_separators(self):
        assert _slugify("..foo") == "foo"


# ---------------------------------------------------------------------------
# _build_key
# ---------------------------------------------------------------------------


class TestBuildKey:
    def test_joins_parts_with_dot(self):
        assert _build_key("arch", "myproject", "structure") == "arch.myproject.structure"

    def test_truncates_to_128(self):
        long = "x" * 200
        key = _build_key("arch", long)
        assert len(key) <= 128

    def test_slugifies_each_part(self):
        key = _build_key("arch", "My Project", "structure")
        assert key == "arch.my.project.structure"


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_value_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_long_value_truncated(self):
        long = "x" * 5000
        assert len(_truncate(long)) == 4096


# ---------------------------------------------------------------------------
# BrainWriteResult
# ---------------------------------------------------------------------------


class TestBrainWriteResult:
    def test_default_values(self):
        r = BrainWriteResult()
        assert r.written == 0
        assert r.skipped == 0
        assert r.failed == 0
        assert r.available is True

    def test_total_property(self):
        r = BrainWriteResult(written=3, skipped=1, failed=1)
        assert r.total == 5

    def test_to_dict_structure(self):
        r = BrainWriteResult(written=2, failed=1, elapsed_ms=12.5)
        d = r.to_dict()
        assert "brain_write" in d
        bw = d["brain_write"]
        assert bw["written"] == 2
        assert bw["failed"] == 1
        assert bw["available"] is True

    def test_to_dict_unavailable(self):
        r = BrainWriteResult(available=False)
        assert r.to_dict()["brain_write"]["available"] is False


# ---------------------------------------------------------------------------
# ArchitectureBrainWriter — tapps-brain unavailable
# ---------------------------------------------------------------------------


class TestBrainWriterUnavailable:
    async def test_returns_unavailable_when_bridge_is_none(self, tmp_path: Path) -> None:
        writer = ArchitectureBrainWriter(tmp_path)
        with patch(
            "tapps_core.brain_bridge.create_brain_bridge",
            return_value=None,
        ):
            result = await writer.write_from_architecture_result(_make_arch_result(), "proj")
        assert result.available is False

    async def test_module_map_returns_unavailable_when_bridge_is_none(
        self, tmp_path: Path
    ) -> None:
        writer = ArchitectureBrainWriter(tmp_path)
        with patch(
            "tapps_core.brain_bridge.create_brain_bridge",
            return_value=None,
        ):
            result = await writer.write_from_module_map(_make_module_map())
        assert result.available is False

    async def test_returns_unavailable_when_factory_raises(self, tmp_path: Path) -> None:
        writer = ArchitectureBrainWriter(tmp_path)
        with patch(
            "tapps_core.brain_bridge.create_brain_bridge",
            side_effect=RuntimeError("dsn invalid"),
        ):
            result = await writer.write_from_architecture_result(_make_arch_result(), "proj")
        assert result.available is False


# ---------------------------------------------------------------------------
# ArchitectureBrainWriter.write_from_architecture_result
# ---------------------------------------------------------------------------


class TestWriteFromArchitectureResult:
    def _make_writer(self, tmp_path: Path) -> tuple[ArchitectureBrainWriter, FakeBridge]:
        bridge = FakeBridge()
        writer = ArchitectureBrainWriter(tmp_path)
        writer._bridge = bridge
        writer._bridge_resolved = True
        return writer, bridge

    async def test_writes_one_entry(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        result = await writer.write_from_architecture_result(_make_arch_result(), "myproject")
        assert result.written == 1
        assert result.failed == 0

    async def test_key_contains_project_name(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "myproject")
        assert len(bridge.calls) == 1
        assert "myproject" in bridge.calls[0]["key"]

    async def test_key_contains_structure(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "myproject")
        assert "structure" in bridge.calls[0]["key"]

    async def test_value_includes_package_count(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(package_count=7), "p")
        assert "7" in bridge.calls[0]["value"]

    async def test_value_includes_module_count(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(module_count=42), "p")
        assert "42" in bridge.calls[0]["value"]

    async def test_tier_is_architectural(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert bridge.calls[0]["tier"] == "architectural"

    async def test_source_agent_is_docs_mcp(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert bridge.calls[0]["source_agent"] == "docs-mcp"

    async def test_tags_include_architecture(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert "architecture" in bridge.calls[0]["tags"]

    async def test_tags_include_docs_mcp(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert "docs-mcp" in bridge.calls[0]["tags"]

    async def test_memory_group_is_insights(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert bridge.calls[0]["memory_group"] == "insights"

    async def test_entry_key_recorded(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        result = await writer.write_from_architecture_result(_make_arch_result(), "myproject")
        assert len(result.entries_written) == 1

    async def test_elapsed_ms_populated(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        result = await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert result.elapsed_ms >= 0.0

    async def test_bridge_exception_counted_as_failed(self, tmp_path: Path) -> None:
        bridge = FakeBridge()
        bridge.save = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        writer = ArchitectureBrainWriter(tmp_path)
        writer._bridge = bridge
        writer._bridge_resolved = True
        result = await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert result.failed == 1
        assert result.written == 0

    async def test_bridge_degraded_response_counted_as_failed(self, tmp_path: Path) -> None:
        # Bridge-open / circuit-open / queued writes report degraded=True;
        # the writer must treat that as a failed write, not a silent success.
        bridge = FakeBridge()
        bridge.save = AsyncMock(  # type: ignore[method-assign]
            return_value={"success": False, "degraded": True, "reason": "circuit open"}
        )
        writer = ArchitectureBrainWriter(tmp_path)
        writer._bridge = bridge
        writer._bridge_resolved = True
        result = await writer.write_from_architecture_result(_make_arch_result(), "p")
        assert result.failed == 1
        assert result.written == 0


# ---------------------------------------------------------------------------
# ArchitectureBrainWriter.write_from_module_map
# ---------------------------------------------------------------------------


class TestWriteFromModuleMap:
    def _make_writer(self, tmp_path: Path) -> tuple[ArchitectureBrainWriter, FakeBridge]:
        bridge = FakeBridge()
        writer = ArchitectureBrainWriter(tmp_path)
        writer._bridge = bridge
        writer._bridge_resolved = True
        return writer, bridge

    async def test_writes_one_entry_per_node(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map(nodes=[_make_module_node("a"), _make_module_node("b")])
        result = await writer.write_from_module_map(mm)
        assert result.written == 2

    async def test_writes_entry_point_entry_when_present(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map(
            nodes=[_make_module_node()],
            entry_points=["cli:main"],
        )
        result = await writer.write_from_module_map(mm)
        assert result.written == 2  # 1 node + 1 entry_points

    async def test_no_entry_point_entry_when_empty(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map(nodes=[_make_module_node()], entry_points=[])
        result = await writer.write_from_module_map(mm)
        assert result.written == 1  # node only

    async def test_key_contains_pkg_and_node_name(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map(project_name="myproj", nodes=[_make_module_node("core")])
        await writer.write_from_module_map(mm)
        pkg_key = bridge.calls[0]["key"]
        assert "myproj" in pkg_key
        assert "core" in pkg_key
        assert "pkg" in pkg_key

    async def test_value_includes_node_name(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map(nodes=[_make_module_node("specialpkg")])
        await writer.write_from_module_map(mm)
        assert "specialpkg" in bridge.calls[0]["value"]

    async def test_value_includes_docstring_first_line(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        node = _make_module_node(module_docstring="Handles authentication.\nMore detail here.")
        mm = _make_module_map(nodes=[node])
        await writer.write_from_module_map(mm)
        assert "Handles authentication" in bridge.calls[0]["value"]

    async def test_value_includes_public_api_count(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        node = _make_module_node(public_api_count=17)
        mm = _make_module_map(nodes=[node])
        await writer.write_from_module_map(mm)
        assert "17" in bridge.calls[0]["value"]

    async def test_caps_at_max_packages(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        nodes = [_make_module_node(f"pkg{i}") for i in range(50)]
        mm = _make_module_map(nodes=nodes)
        result = await writer.write_from_module_map(mm)
        # 30 packages max, no entry points
        assert result.written == 30

    async def test_empty_module_tree(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map(nodes=[])
        result = await writer.write_from_module_map(mm)
        assert result.written == 0

    async def test_tier_is_architectural(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map()
        await writer.write_from_module_map(mm)
        assert bridge.calls[0]["tier"] == "architectural"

    async def test_memory_group_is_insights(self, tmp_path: Path) -> None:
        writer, bridge = self._make_writer(tmp_path)
        mm = _make_module_map()
        await writer.write_from_module_map(mm)
        assert bridge.calls[0]["memory_group"] == "insights"
