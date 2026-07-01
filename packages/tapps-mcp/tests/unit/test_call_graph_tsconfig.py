"""Unit tests for tsconfig path-alias resolution (TAP-4540).

Covers the ``{"@/*": ["src/*"]}`` wildcard form, exact aliases, baseUrl
handling, and the honest-negative cases (missing / malformed config, no match)
required by the deterministic contract (ADR-0004).
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph_tsconfig import (
    TsconfigPaths,
    load_tsconfig_paths,
    resolve_path_alias,
)


def _write_tsconfig(tmp_path: Path, body: str) -> Path:
    (tmp_path / "tsconfig.json").write_text(body, encoding="utf-8")
    return tmp_path


class TestLoadTsconfigPaths:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        cfg = load_tsconfig_paths(tmp_path)
        assert cfg.is_empty()
        assert cfg.aliases == {}

    def test_wildcard_alias_loads(self, tmp_path: Path) -> None:
        _write_tsconfig(
            tmp_path,
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}',
        )
        cfg = load_tsconfig_paths(tmp_path)
        assert not cfg.is_empty()
        assert cfg.aliases == {"@/*": ["src/*"]}
        assert cfg.base_url == "."

    def test_malformed_json_degrades_to_empty(self, tmp_path: Path) -> None:
        # Trailing comma / comments — not standard JSON. Degrade, never crash.
        _write_tsconfig(tmp_path, '{"compilerOptions": {"paths": {"@/*": ["src/*"]},}}')
        cfg = load_tsconfig_paths(tmp_path)
        assert cfg.is_empty()

    def test_no_paths_block_is_empty(self, tmp_path: Path) -> None:
        _write_tsconfig(tmp_path, '{"compilerOptions": {"baseUrl": "src"}}')
        cfg = load_tsconfig_paths(tmp_path)
        assert cfg.is_empty()

    def test_default_base_url_when_absent(self, tmp_path: Path) -> None:
        _write_tsconfig(tmp_path, '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}}')
        cfg = load_tsconfig_paths(tmp_path)
        assert cfg.base_url == "."


class TestResolvePathAlias:
    def test_wildcard_alias_resolves_to_module(self) -> None:
        cfg = TsconfigPaths(base_url=".", aliases={"@/*": ["src/*"]})
        # @/util -> src/util -> module "util" (leading src/ stripped).
        assert resolve_path_alias(cfg, "@/util") == "util"

    def test_wildcard_alias_nested(self) -> None:
        cfg = TsconfigPaths(base_url=".", aliases={"@/*": ["src/*"]})
        assert resolve_path_alias(cfg, "@/a/b/util") == "a/b/util"

    def test_no_src_prefix_target(self) -> None:
        cfg = TsconfigPaths(base_url=".", aliases={"~/*": ["lib/*"]})
        assert resolve_path_alias(cfg, "~/thing") == "lib/thing"

    def test_exact_alias_resolves(self) -> None:
        cfg = TsconfigPaths(base_url=".", aliases={"@app": ["src/app/index"]})
        assert resolve_path_alias(cfg, "@app") == "app/index"

    def test_base_url_prepended(self) -> None:
        # baseUrl "packages" + target "src/util" -> packages/src/util ->
        # (only a *leading* src is stripped) -> packages/src/util.
        cfg = TsconfigPaths(base_url="packages", aliases={"@/*": ["mod/*"]})
        assert resolve_path_alias(cfg, "@/util") == "packages/mod/util"

    def test_empty_config_returns_none(self) -> None:
        assert resolve_path_alias(TsconfigPaths(), "@/util") is None

    def test_non_matching_specifier_returns_none(self) -> None:
        cfg = TsconfigPaths(base_url=".", aliases={"@/*": ["src/*"]})
        assert resolve_path_alias(cfg, "#/util") is None
        assert resolve_path_alias(cfg, "./relative") is None

    def test_longest_alias_wins(self) -> None:
        cfg = TsconfigPaths(
            base_url=".",
            aliases={"@/*": ["src/*"], "@/features/*": ["src/features/*"]},
        )
        # The more specific alias must be tried first.
        assert resolve_path_alias(cfg, "@/features/x") == "features/x"
