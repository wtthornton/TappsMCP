"""Doctor checks for ADR-0014 brain doc cutover."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tapps_mcp.distribution.doctor import (
    check_brain_docs_tools,
    check_consumer_context7_env,
    check_legacy_doc_cache,
)


def test_legacy_doc_cache_skipped_when_disabled(tmp_path: Path) -> None:
    os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    result = check_legacy_doc_cache(tmp_path)
    assert result.ok is True
    assert "disabled" in result.message


def test_legacy_doc_cache_fails_with_subdirs(tmp_path: Path) -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    lib_dir = tmp_path / ".tapps-mcp-cache" / "pytest"
    lib_dir.mkdir(parents=True)
    (lib_dir / "fixtures.meta.json").write_text(
        json.dumps({"library": "pytest", "topic": "fixtures"}),
        encoding="utf-8",
    )
    try:
        result = check_legacy_doc_cache(tmp_path)
        assert result.ok is False
        assert "legacy doc" in result.message.lower()
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def test_consumer_context7_warns_when_present(tmp_path: Path) -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    mcp = {
        "mcpServers": {
            "nlt-code-quality": {
                "env": {"TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}"},
            }
        }
    }
    (tmp_path / ".mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    try:
        result = check_consumer_context7_env(tmp_path)
        assert result.ok is True
        assert "Context7" in result.message
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def test_brain_docs_tools_skipped_when_disabled(tmp_path: Path) -> None:
    os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    result = check_brain_docs_tools(tmp_path)
    assert result.ok is True
    assert "disabled" in result.message


def test_brain_docs_tools_fails_without_http_url(tmp_path: Path, monkeypatch) -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    monkeypatch.setattr(
        "tapps_mcp.distribution.doctor._brain_http_url_for_checks",
        lambda _root: "",
    )
    try:
        result = check_brain_docs_tools(tmp_path)
        assert result.ok is False
        assert "HTTP brain" in result.message
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def test_brain_docs_tools_passes_on_probe_ok(tmp_path: Path, monkeypatch) -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "quality_preset: standard\nmemory:\n  brain_http_url: http://localhost:8080\n"
    )
    monkeypatch.setattr(
        "tapps_mcp.distribution.doctor._run_docs_tools_probe",
        lambda _url, _settings: {"ok": True, "http_status": 200},
    )
    try:
        result = check_brain_docs_tools(tmp_path)
        assert result.ok is True
        assert "docs_lookup probe ok" in result.message
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def _seed_project(tmp_path: Path) -> None:
    os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")


def test_context7_live_quick_mode_skips(tmp_path: Path) -> None:
    from tapps_mcp.distribution.doctor import check_context7_live

    _seed_project(tmp_path)
    result = check_context7_live(tmp_path, quick=True)
    assert result.ok is True
    assert "quick" in result.message.lower()


def test_context7_live_unauthorized_warns(tmp_path: Path, monkeypatch) -> None:
    from tapps_core.common.models import Context7Diagnostic
    from tapps_mcp.distribution.doctor import check_context7_live

    _seed_project(tmp_path)
    monkeypatch.setattr(
        "tapps_mcp.diagnostics.probe_context7",
        lambda *_a, **_k: Context7Diagnostic(
            api_key_set=True, status="unauthorized", reachable=True, http_status=401
        ),
    )
    result = check_context7_live(tmp_path)
    assert result.ok is False
    assert "rejected" in result.message.lower()


def test_context7_live_available_passes(tmp_path: Path, monkeypatch) -> None:
    from tapps_core.common.models import Context7Diagnostic
    from tapps_mcp.distribution.doctor import check_context7_live

    _seed_project(tmp_path)
    monkeypatch.setattr(
        "tapps_mcp.diagnostics.probe_context7",
        lambda *_a, **_k: Context7Diagnostic(
            api_key_set=True, status="available", reachable=True, latency_ms=42.0
        ),
    )
    result = check_context7_live(tmp_path)
    assert result.ok is True
    assert "reachable" in result.message.lower()


def test_context7_live_skipped_when_brain_routing(tmp_path: Path) -> None:
    from tapps_mcp.distribution.doctor import check_context7_live

    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    try:
        result = check_context7_live(tmp_path)
        assert result.ok is True
        assert "docs_via_brain" in result.message
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
