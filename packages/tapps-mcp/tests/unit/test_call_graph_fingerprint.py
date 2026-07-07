"""Tests for call-graph fingerprint helpers (TAP-4077, TAP-4078)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.project import call_graph_fingerprint
from tapps_mcp.project.call_graph_fingerprint import (
    compute_index_fingerprint,
    compute_per_file_fingerprints,
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


class TestTypeScriptFingerprint:
    """TAP-4537: .ts/.tsx files and grammar version affect the fingerprint."""

    def _write(self, root: Path, rel: str, body: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_ts_file_presence_changes_fingerprint(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        before = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        self._write(tmp_path, "demo/widget.ts", "export const x = 1;\n")
        after = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert before != after

    def test_ts_file_edit_changes_fingerprint(self, tmp_path: Path) -> None:
        ts = self._write(tmp_path, "demo/widget.ts", "export const x = 1;\n")
        settings = fingerprint_settings(tmp_path)
        before = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        ts.write_text("export const x = 2;\n", encoding="utf-8")
        after = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert before != after

    def test_tsx_file_presence_changes_fingerprint(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        before = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        self._write(tmp_path, "demo/Comp.tsx", "export const C = () => null;\n")
        after = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert before != after

    def test_grammar_version_change_changes_fingerprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        monkeypatch.setattr(call_graph_fingerprint, "_ts_grammar_version", lambda: "0.23.2")
        before = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        monkeypatch.setattr(call_graph_fingerprint, "_ts_grammar_version", lambda: "0.24.0")
        after = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert before != after

    def test_grammar_absent_sentinel_is_stable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        monkeypatch.setattr(call_graph_fingerprint, "_ts_grammar_version", lambda: "absent")
        fp1 = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        fp2 = compute_index_fingerprint(settings, index_version=INDEX_VERSION)
        assert fp1 == fp2


class TestPerFileFingerprints:
    """Per-file content fingerprints for incremental re-index (TAP-4533)."""

    def test_maps_each_source_file(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "demo/a.py")
        _write_py(tmp_path, "demo/b.py")
        settings = fingerprint_settings(tmp_path)
        fps = compute_per_file_fingerprints(settings)
        assert set(fps) == {"demo/a.py", "demo/b.py"}
        assert all(isinstance(v, str) and v for v in fps.values())

    def test_only_changed_file_hash_differs(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "demo/a.py")
        _write_py(tmp_path, "demo/b.py")
        settings = fingerprint_settings(tmp_path)
        before = compute_per_file_fingerprints(settings)
        # Mutate only b.py — the changed subset must be exactly {"demo/b.py"}.
        _write_py(tmp_path, "demo/b.py", body="def other():\n    return 9\n")
        after = compute_per_file_fingerprints(settings)
        changed = {k for k in after if after[k] != before.get(k)}
        assert changed == {"demo/b.py"}
        assert after["demo/a.py"] == before["demo/a.py"]

    def test_content_hash_stable_across_touch(self, tmp_path: Path) -> None:
        # Content-based (not mtime): rewriting identical bytes must not change it.
        path = _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        first = compute_per_file_fingerprints(settings)
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        second = compute_per_file_fingerprints(settings)
        assert first == second

    def test_added_and_deleted_reflected(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "demo/a.py")
        settings = fingerprint_settings(tmp_path)
        assert set(compute_per_file_fingerprints(settings)) == {"demo/a.py"}
        _write_py(tmp_path, "demo/c.py")
        (tmp_path / "demo/a.py").unlink()
        assert set(compute_per_file_fingerprints(settings)) == {"demo/c.py"}
