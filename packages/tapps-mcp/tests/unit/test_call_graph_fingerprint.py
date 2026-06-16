"""Tests for call-graph fingerprint helpers (TAP-4077, TAP-4078)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph_fingerprint import (
    compute_index_fingerprint,
    fingerprint_settings,
)
from tapps_mcp.project.call_graph_types import INDEX_VERSION


def _write_py(root: Path, rel: str, body: str = "def fn():\n    pass\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestFingerprintSettings:
    def test_shared_settings_match_build_and_summarize(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        fp1 = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        fp2 = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert fp1 == fp2

    def test_mtime_fingerprint_changes_on_edit(self, tmp_path: Path) -> None:
        path = _write_py(tmp_path, "demo/b.py")
        settings = fingerprint_settings(tmp_path)
        before = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        path.write_text("def fn():\n    return 1\n", encoding="utf-8")
        after = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert before != after

    def test_git_repo_uses_head_component(self, tmp_path: Path) -> None:
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        _write_py(tmp_path, "pkg/mod.py")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env={
                **dict(__import__("os").environ),
                "GIT_AUTHOR_NAME": "test",
                "GIT_AUTHOR_EMAIL": "t@test.com",
                "GIT_COMMITTER_NAME": "test",
                "GIT_COMMITTER_EMAIL": "t@test.com",
            },
        )
        settings = fingerprint_settings(tmp_path)
        fp = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert len(fp) == 16
