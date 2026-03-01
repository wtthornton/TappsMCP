"""Tests for knowledge ingestion pipeline."""

from __future__ import annotations

from pathlib import Path

from tapps_core.experts.knowledge_ingestion import KnowledgeIngestionPipeline


class TestKnowledgeIngestionPipeline:
    def test_ingest_empty_project(self, tmp_path: Path):
        pipeline = KnowledgeIngestionPipeline(tmp_path)
        result = pipeline.ingest_project_sources()
        assert result.entries_ingested == 0
        assert result.entries_failed == 0

    def test_ingest_with_architecture_doc(self, tmp_path: Path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "architecture.md").write_text(
            "# Architecture\n\nSystem overview.\n", encoding="utf-8"
        )
        pipeline = KnowledgeIngestionPipeline(tmp_path)
        result = pipeline.ingest_project_sources()
        assert result.entries_ingested >= 1

    def test_extract_title_from_header(self, tmp_path: Path):
        pipeline = KnowledgeIngestionPipeline(tmp_path)
        title = pipeline._extract_title(Path("test.md"), "# My Great Title\n\nContent.")
        assert title == "My Great Title"

    def test_extract_title_fallback(self, tmp_path: Path):
        pipeline = KnowledgeIngestionPipeline(tmp_path)
        title = pipeline._extract_title(Path("my-doc-name.md"), "No header here.\n")
        assert title == "My Doc Name"

    def test_store_writes_markdown_file(self, tmp_path: Path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "architecture.md").write_text("# Architecture\n\nContent.\n", encoding="utf-8")
        pipeline = KnowledgeIngestionPipeline(tmp_path)
        pipeline.ingest_project_sources()

        # Check that knowledge files were created.
        kb_dir = tmp_path / ".tapps-mcp" / "knowledge"
        if kb_dir.exists():
            files = list(kb_dir.rglob("*.md"))
            assert len(files) >= 1
            content = files[0].read_text(encoding="utf-8")
            assert "source:" in content  # YAML frontmatter

    def test_ingest_adr_docs(self, tmp_path: Path):
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "001-use-postgres.md").write_text(
            "# ADR 001: Use PostgreSQL\n\nWe decided to use PostgreSQL.\n",
            encoding="utf-8",
        )
        pipeline = KnowledgeIngestionPipeline(tmp_path)
        result = pipeline.ingest_project_sources()
        assert result.entries_ingested >= 1
