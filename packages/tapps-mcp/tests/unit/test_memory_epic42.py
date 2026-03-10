"""Unit tests for Epic 42: tapps_memory 2026 Enhancements.

Tests cover:
- 42.1: Ranked BM25 search via MCP
- 42.2: Missing actions (contradictions, reseed, import, export)
- 42.3: Outcome-oriented search/list responses (summaries, limits)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_memory_tools import tapps_memory


async def _noop_init() -> None:
    """Async no-op replacement for ensure_session_initialized."""


@pytest.fixture(autouse=True)
def _mock_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip session initialization in tests."""
    monkeypatch.setattr(
        "tapps_mcp.server_memory_tools.ensure_session_initialized",
        _noop_init,
    )


@pytest.fixture()
def mock_store(tmp_path: Path):  # noqa: ANN201
    """Create a real MemoryStore backed by tmp_path and patch _get_memory_store."""
    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    with patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store):
        yield store


# ---------------------------------------------------------------------------
# 42.1 — Ranked BM25 Search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestRankedSearch:
    """Story 42.1: Ranked BM25 search via MCP."""

    async def test_ranked_search_returns_scores(self, mock_store: object) -> None:
        """Ranked search results include score, effective_confidence, stale."""
        await tapps_memory(action="save", key="arch-db", value="Use PostgreSQL for the database")
        result = await tapps_memory(action="search", query="PostgreSQL database")
        assert result["success"] is True
        data = result["data"]
        assert data["ranked"] is True
        assert data["returned_count"] >= 1
        first = data["results"][0]
        assert "score" in first
        assert "effective_confidence" in first
        assert "stale" in first
        assert isinstance(first["score"], float)

    async def test_ranked_search_default(self, mock_store: object) -> None:
        """Default search is ranked (ranked=True is default)."""
        await tapps_memory(action="save", key="k1", value="test value")
        result = await tapps_memory(action="search", query="test")
        assert result["data"]["ranked"] is True

    async def test_unranked_search(self, mock_store: object) -> None:
        """ranked=False returns unranked FTS5-only results."""
        await tapps_memory(action="save", key="k1", value="test value")
        result = await tapps_memory(action="search", query="test", ranked=False)
        assert result["data"]["ranked"] is False
        # Unranked results are plain dicts without score
        if result["data"]["returned_count"] > 0:
            first = result["data"]["results"][0]
            assert "score" not in first

    async def test_ranked_search_limit_respected(self, mock_store: object) -> None:
        """Limit parameter is respected in ranked search."""
        for i in range(5):
            await tapps_memory(action="save", key=f"item-{i}", value=f"test item number {i}")
        result = await tapps_memory(action="search", query="test item", limit=2)
        assert result["data"]["returned_count"] <= 2

    async def test_ranked_search_stale_flag(self, mock_store: object) -> None:
        """Fresh entries have stale=False."""
        await tapps_memory(action="save", key="fresh-key", value="Fresh content")
        result = await tapps_memory(action="search", query="Fresh content")
        if result["data"]["returned_count"] > 0:
            assert result["data"]["results"][0]["stale"] is False

    async def test_ranked_search_empty_query(self, mock_store: object) -> None:
        """Empty query with tags falls back to unranked."""
        await tapps_memory(
            action="save", key="tagged", value="tagged value", tags="mylib",
        )
        result = await tapps_memory(action="search", tags="mylib", ranked=True)
        # tags-only search falls back to unranked since there's no query
        assert result["data"]["ranked"] is False

    async def test_search_response_has_total_and_returned_count(
        self, mock_store: object,
    ) -> None:
        """Search responses include total_count and returned_count."""
        await tapps_memory(action="save", key="k1", value="search term here")
        result = await tapps_memory(action="search", query="search term")
        data = result["data"]
        assert "total_count" in data
        assert "returned_count" in data


# ---------------------------------------------------------------------------
# 42.2 — Wire Missing Actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestContradictions:
    """Story 42.2: contradictions action."""

    async def test_contradictions_returns_list(self, mock_store: object) -> None:
        """Contradictions action returns structured result."""
        mock_profile = MagicMock()
        mock_profile.tech_stack.libraries = ["ruff"]
        mock_profile.tech_stack.frameworks = []
        mock_profile.test_frameworks = ["pytest"]
        mock_profile.package_managers = ["uv"]
        mock_profile.ci_systems = []
        mock_profile.has_docker = False
        mock_profile.project_type = "library"
        mock_profile.project_type_confidence = 0.8

        with (
            patch(
                "tapps_mcp.project.profiler.detect_project_profile",
                return_value=mock_profile,
            ),
            patch("tapps_core.config.settings.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = Path("/tmp/test")
            result = await tapps_memory(action="contradictions")

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "contradictions"
        assert "contradictions" in data
        assert "count" in data
        assert "checked_count" in data
        assert "store_metadata" in data

    async def test_contradictions_detects_issues(self, mock_store: object) -> None:
        """Contradictions detects a memory that disagrees with project state."""
        await tapps_memory(
            action="save", key="web-fw",
            value="We use django for the web framework",
            tags="framework",
        )

        mock_profile = MagicMock()
        mock_profile.tech_stack.libraries = ["ruff"]
        mock_profile.tech_stack.frameworks = ["fastapi"]
        mock_profile.test_frameworks = ["pytest"]
        mock_profile.package_managers = ["uv"]
        mock_profile.ci_systems = []
        mock_profile.has_docker = False

        with (
            patch(
                "tapps_mcp.project.profiler.detect_project_profile",
                return_value=mock_profile,
            ),
            patch("tapps_core.config.settings.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = Path("/tmp/test")
            result = await tapps_memory(action="contradictions")

        data = result["data"]
        assert data["count"] >= 1
        assert any("django" in c["reason"] for c in data["contradictions"])


@pytest.mark.asyncio()
class TestReseed:
    """Story 42.2: reseed action."""

    async def test_reseed_returns_result(self, mock_store: object) -> None:
        """Reseed action calls reseed_from_profile and returns summary."""
        mock_profile = MagicMock()
        mock_profile.project_type = "library"
        mock_profile.project_type_confidence = 0.9
        mock_profile.tech_stack.languages = ["Python"]
        mock_profile.tech_stack.frameworks = []
        mock_profile.test_frameworks = ["pytest"]
        mock_profile.package_managers = ["uv"]
        mock_profile.ci_systems = []
        mock_profile.has_docker = False

        with (
            patch(
                "tapps_mcp.project.profiler.detect_project_profile",
                return_value=mock_profile,
            ),
            patch("tapps_core.config.settings.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = Path("/tmp/test")
            result = await tapps_memory(action="reseed")

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "reseed"
        assert "seeded_count" in data
        assert "store_metadata" in data


@pytest.mark.asyncio()
class TestImportExport:
    """Story 42.2: import and export actions."""

    async def test_export_creates_file(
        self, mock_store: object, tmp_path: Path,
    ) -> None:
        """Export writes memories to a JSON file."""
        await tapps_memory(action="save", key="k1", value="v1")

        export_path = str(tmp_path / "export.json")

        with patch("tapps_core.config.settings.load_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = await tapps_memory(
                action="export", file_path=export_path,
            )

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "export"
        assert data["exported_count"] == 1
        assert Path(data["file_path"]).exists()

        # Verify JSON is valid
        content = json.loads(Path(data["file_path"]).read_text())
        assert "memories" in content

    async def test_import_reads_file(
        self, mock_store: object, tmp_path: Path,
    ) -> None:
        """Import reads memories from a JSON file."""
        # Create export file first
        export_data = {
            "memories": [
                {
                    "key": "imported-key",
                    "value": "imported value",
                    "tier": "pattern",
                    "scope": "project",
                    "source": "agent",
                    "source_agent": "test",
                    "tags": [],
                    "confidence": 0.8,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "last_accessed": "2026-01-01T00:00:00+00:00",
                    "access_count": 0,
                    "reinforce_count": 0,
                    "contradicted": False,
                },
            ],
            "exported_at": "2026-01-01T00:00:00Z",
            "entry_count": 1,
        }
        import_path = tmp_path / "import.json"
        import_path.write_text(json.dumps(export_data))

        with patch("tapps_core.config.settings.load_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = await tapps_memory(
                action="import", file_path=str(import_path),
            )

        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "import"
        assert data["imported_count"] == 1

    async def test_import_respects_overwrite(
        self, mock_store: object, tmp_path: Path,
    ) -> None:
        """Import skips existing keys by default, overwrites when overwrite=True."""
        await tapps_memory(action="save", key="existing-key", value="original")

        export_data = {
            "memories": [
                {
                    "key": "existing-key",
                    "value": "new value",
                    "tier": "pattern",
                    "scope": "project",
                    "source": "agent",
                    "source_agent": "test",
                    "tags": [],
                    "confidence": 0.8,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "last_accessed": "2026-01-01T00:00:00+00:00",
                    "access_count": 0,
                    "reinforce_count": 0,
                    "contradicted": False,
                },
            ],
            "exported_at": "2026-01-01T00:00:00Z",
            "entry_count": 1,
        }
        import_path = tmp_path / "import.json"
        import_path.write_text(json.dumps(export_data))

        with patch("tapps_core.config.settings.load_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path

            # Without overwrite: skip
            r1 = await tapps_memory(action="import", file_path=str(import_path))
            assert r1["data"]["skipped_count"] == 1

            # With overwrite: import
            r2 = await tapps_memory(
                action="import", file_path=str(import_path), overwrite=True,
            )
            assert r2["data"]["imported_count"] == 1

    async def test_import_missing_file_path(self, mock_store: object) -> None:
        """Import without file_path returns error."""
        result = await tapps_memory(action="import")
        assert result["data"]["error"] == "missing_file_path"

    async def test_export_filters(
        self, mock_store: object, tmp_path: Path,
    ) -> None:
        """Export respects tier and confidence filters."""
        await tapps_memory(
            action="save", key="arch", value="Arch decision",
            tier="architectural",
        )
        await tapps_memory(
            action="save", key="ctx", value="Context note",
            tier="context",
        )

        export_path = str(tmp_path / "filtered.json")

        with patch("tapps_core.config.settings.load_settings") as mock_settings:
            mock_settings.return_value.project_root = tmp_path
            result = await tapps_memory(
                action="export", file_path=export_path,
                tier="architectural",
            )

        assert result["success"] is True
        assert result["data"]["exported_count"] == 1


# ---------------------------------------------------------------------------
# 42.3 — Outcome-Oriented Responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestCuratedResponses:
    """Story 42.3: Curated search/list responses."""

    async def test_list_has_total_and_returned_count(
        self, mock_store: object,
    ) -> None:
        """List response includes total_count and returned_count."""
        for i in range(3):
            await tapps_memory(action="save", key=f"k{i}", value=f"v{i}")
        result = await tapps_memory(action="list")
        data = result["data"]
        assert data["total_count"] == 3
        assert data["returned_count"] == 3

    async def test_list_limit_enforced(self, mock_store: object) -> None:
        """List with limit returns at most limit entries."""
        for i in range(10):
            await tapps_memory(action="save", key=f"k{i}", value=f"v{i}")
        result = await tapps_memory(action="list", limit=3)
        data = result["data"]
        assert data["total_count"] == 10
        assert data["returned_count"] == 3

    async def test_list_summary_truncation(self, mock_store: object) -> None:
        """List shows summaries for entries past the threshold."""
        for i in range(8):
            await tapps_memory(
                action="save", key=f"k{i}",
                value=f"A very long value that should be summarized {i} " * 5,
            )
        result = await tapps_memory(action="list", include_summary=True)
        data = result["data"]

        # First 5 entries should have full data (model_dump includes "value")
        for entry in data["entries"][:5]:
            assert "value" in entry

        # Entries past threshold should have "summary" instead
        for entry in data["entries"][5:]:
            assert "summary" in entry
            assert "value" not in entry

    async def test_list_no_summary(self, mock_store: object) -> None:
        """List with include_summary=False returns full entries for all."""
        for i in range(8):
            await tapps_memory(action="save", key=f"k{i}", value=f"v{i}")
        result = await tapps_memory(action="list", include_summary=False)
        for entry in result["data"]["entries"]:
            assert "value" in entry

    async def test_search_summary_truncation(self, mock_store: object) -> None:
        """Ranked search shows summaries past the threshold."""
        for i in range(8):
            await tapps_memory(
                action="save", key=f"item-{i}",
                value=f"Test search item with long content number {i} " * 5,
            )
        result = await tapps_memory(
            action="search", query="Test search item", limit=8,
        )
        data = result["data"]
        if data["returned_count"] > 5:
            # Entries past threshold should have summary in entry dict
            sixth = data["results"][5]["entry"]
            assert "summary" in sixth


# ---------------------------------------------------------------------------
# Validation & 11-action coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestValidActions:
    """Verify all actions are in _VALID_ACTIONS."""

    async def test_all_actions_valid(self) -> None:
        """All documented actions are accepted."""
        from tapps_mcp.server_memory_tools import _VALID_ACTIONS

        expected = {
            "save", "save_bulk", "get", "list", "delete", "search",
            "reinforce", "gc", "contradictions", "reseed",
            "import", "export", "consolidate", "unconsolidate",
            "federate_register", "federate_publish", "federate_subscribe",
            "federate_sync", "federate_search", "federate_status",
            "index_session", "validate", "maintain",
        }
        assert _VALID_ACTIONS == expected
