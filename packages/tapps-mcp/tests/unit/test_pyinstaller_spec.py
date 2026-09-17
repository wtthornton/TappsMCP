"""Tests verifying the PyInstaller spec derives its hidden imports from the tree.

TAP-6887 added a drift check over a hand-maintained list of ~408 module names in
``tapps_mcp.spec``. It worked -- it caught ``tapps_mcp.project.static_detectors``
-- but it could only ever catch the drift *after* it shipped, and the list had
already accumulated four duplicate entries by the time it did.

TAP-7768 removes the class instead of re-detecting it: the spec now derives the
``tapps_mcp`` half of ``hiddenimports`` by walking the source tree, exactly as it
already derives ``datas``. A new module is covered the moment it exists, and a
deleted one cannot leave a stale entry behind.

That moves what these tests must guard. Asserting "every module appears in the
list" against a derived list is tautological -- it cannot go red. So these tests
guard the *derivation*: that it is still live, still aimed at the real source
tree, still picks up a module it has never seen, and has not quietly reverted to
a literal list.

They also execute the spec, which nothing else in this repo does. PyInstaller is
not a dev dependency and no CI job builds the binary, so a spec that raised at
build time would otherwise reach a release unnoticed -- which matters more since
TAP-7768 moved real logic into it.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple, cast
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_SPEC_FILE = _REPO_ROOT / "tapps_mcp.spec"
_SRC_DIR = _PACKAGE_ROOT / "src" / "tapps_mcp"

_DISCOVERY_FUNC = "_discover_modules"

# Hand-maintained in the spec, and legitimately so: these are not in the source
# tree, so nothing can derive them. They can still go stale if a dependency is
# dropped, which is what test_third_party_hidden_imports_resolve checks.
_THIRD_PARTY = (
    "click",
    "pydantic",
    "pydantic_settings",
    "structlog",
    "yaml",
    "anyio",
    "httpx",
    "filelock",
    "mcp",
    "mcp.server",
    "mcp.server.fastmcp",
)


class LoadedSpec(NamedTuple):
    """The executed spec, plus the arguments it passed to ``Analysis``."""

    module: ModuleType
    analysis_kwargs: dict[str, Any]


def _stub_pyinstaller(capture: dict[str, Any]) -> dict[str, ModuleType]:
    """Build stand-in PyInstaller modules that record rather than build."""

    class _Analysis:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            capture.update(kwargs)
            self.pure: list[Any] = []
            self.scripts: list[Any] = []
            self.binaries: list[Any] = []
            self.datas: list[Any] = []

    class _Noop:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    api = ModuleType("PyInstaller.building.api")
    api.__dict__.update({"COLLECT": _Noop, "EXE": _Noop, "PYZ": _Noop})
    build_main = ModuleType("PyInstaller.building.build_main")
    build_main.__dict__.update({"Analysis": _Analysis})

    return {
        "PyInstaller": ModuleType("PyInstaller"),
        "PyInstaller.building": ModuleType("PyInstaller.building"),
        "PyInstaller.building.api": api,
        "PyInstaller.building.build_main": build_main,
    }


@pytest.fixture(scope="module")
def loaded_spec(tmp_path_factory: pytest.TempPathFactory) -> LoadedSpec:
    """Execute ``tapps_mcp.spec`` and hand back the module and its Analysis args.

    The spec is not importable where it sits -- ``.spec`` is not a module suffix,
    and it builds a PyInstaller ``Analysis`` at module level -- so copy it to a
    ``.py`` file and import that, with PyInstaller stubbed so no build toolchain
    is needed. Importing it rather than reading it means every test below runs
    against the real code the build runs.

    The spec resolves its source directories relative to the repo root, so the
    import happens from there.
    """
    if not _SPEC_FILE.exists():
        pytest.fail(f"{_SPEC_FILE} not found -- the build spec is not optional.")

    copied = tmp_path_factory.mktemp("spec") / "tapps_mcp_spec_under_test.py"
    copied.write_text(_SPEC_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    capture: dict[str, Any] = {}
    import_spec = importlib.util.spec_from_file_location(copied.stem, copied)
    assert import_spec is not None and import_spec.loader is not None
    module = importlib.util.module_from_spec(import_spec)

    cwd = Path.cwd()
    with mock.patch.dict(sys.modules, _stub_pyinstaller(capture)):
        try:
            os.chdir(_REPO_ROOT)
            import_spec.loader.exec_module(module)
        finally:
            os.chdir(cwd)

    return LoadedSpec(module=module, analysis_kwargs=capture)


def _discovery(loaded: LoadedSpec) -> Callable[[Path], list[str]]:
    """Fetch the spec's own discovery function, failing loudly if it is gone."""
    func = getattr(loaded.module, _DISCOVERY_FUNC, None)
    if not callable(func):
        pytest.fail(
            f"{_SPEC_FILE.name} defines no {_DISCOVERY_FUNC}() -- hiddenimports is "
            f"not derived from the source tree (TAP-7768)."
        )
    # The spec is loaded dynamically, so its members carry no static type.
    return cast("Callable[[Path], list[str]]", func)


def _walk_source_tree(src_dir: Path) -> set[str]:
    """Independently enumerate dotted module names under a source directory.

    Deliberately a second implementation, not a call into the spec's: this is the
    reference the spec's derivation is measured against.
    """
    modules: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        parts = list(py_file.relative_to(src_dir.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            modules.add(".".join(parts[:-1]))
        else:
            modules.add(".".join(parts))
    return modules


class TestDerivation:
    def test_spec_defines_a_discovery_function(self, loaded_spec: LoadedSpec) -> None:
        """The spec must derive its module list, not restate one."""
        assert callable(_discovery(loaded_spec))

    def test_spec_does_not_hardcode_submodule_names(self) -> None:
        """No literal ``tapps_mcp.<submodule>`` strings may remain in the spec.

        This is the regression guard for TAP-7768: re-adding a hand-typed list
        beside the derivation reintroduces exactly the drift the derivation
        removes, and would otherwise pass every other test here.
        """
        text = _SPEC_FILE.read_text(encoding="utf-8")
        literals = sorted(set(re.findall(r'"(tapps_mcp\.[^"]*)"', text)))
        assert not literals, (
            f"{len(literals)} hardcoded tapps_mcp submodule literal(s) in "
            f"{_SPEC_FILE.name}; hiddenimports must be derived by "
            f"{_DISCOVERY_FUNC}():\n" + "\n".join(f"  - {m}" for m in literals)
        )

    def test_derivation_covers_the_real_source_tree(self, loaded_spec: LoadedSpec) -> None:
        """Aimed at the real tree, the derivation must return all of it.

        Goes red if the walk is pointed at the wrong directory, stops recursing,
        or returns nothing -- the ways a derivation fails silently.
        """
        derived = set(_discovery(loaded_spec)(_SRC_DIR))
        expected = _walk_source_tree(_SRC_DIR)

        assert derived, f"{_DISCOVERY_FUNC}() returned nothing for {_SRC_DIR}"
        assert "tapps_mcp.server" in derived, (
            "derivation is not walking the tapps_mcp source tree "
            f"(got {len(derived)} names, none of them tapps_mcp.server)"
        )
        assert derived == expected, (
            f"derivation disagrees with the source tree:\n"
            f"  missing: {sorted(expected - derived)}\n"
            f"  extra:   {sorted(derived - expected)}"
        )

    def test_derivation_picks_up_a_module_it_has_never_seen(
        self, loaded_spec: LoadedSpec, tmp_path: Path
    ) -> None:
        """A brand-new module must be covered without editing the spec.

        This is the property TAP-7768 buys and the one the old hand-maintained
        list could not hold. It fails if the derivation is ever swapped back for
        a fixed collection, even one that happens to be correct today.
        """
        src = tmp_path / "tapps_mcp"
        (src / "nested").mkdir(parents=True)
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "brand_new_module.py").write_text("", encoding="utf-8")
        (src / "nested" / "__init__.py").write_text("", encoding="utf-8")
        (src / "nested" / "deep_new_module.py").write_text("", encoding="utf-8")

        derived = set(_discovery(loaded_spec)(src))

        assert derived == {
            "tapps_mcp",
            "tapps_mcp.brand_new_module",
            "tapps_mcp.nested",
            "tapps_mcp.nested.deep_new_module",
        }, f"derivation did not enumerate a fresh tree correctly: {sorted(derived)}"


class TestExecutedSpec:
    def test_hidden_imports_are_complete_and_free_of_duplicates(
        self, loaded_spec: LoadedSpec
    ) -> None:
        """Check what the spec actually hands PyInstaller, not what it looks like.

        Reaching this test at all proves the spec executes; the assertions cover
        what it produced.
        """
        hidden = loaded_spec.analysis_kwargs.get("hiddenimports")
        assert isinstance(hidden, list) and hidden, "spec produced no hiddenimports"

        duplicates = sorted({h for h in hidden if hidden.count(h) > 1})
        assert not duplicates, (
            f"{len(duplicates)} duplicate hidden import(s) -- the hand-maintained "
            f"list carried four of these before TAP-7768: {duplicates}"
        )
        assert set(_THIRD_PARTY) <= set(hidden)
        assert _walk_source_tree(_SRC_DIR) <= set(hidden), (
            "the executed spec does not cover the whole source tree"
        )

    def test_spec_collects_data_files(self, loaded_spec: LoadedSpec) -> None:
        """The packaged knowledge/config assets must still be collected."""
        datas = loaded_spec.analysis_kwargs.get("datas")
        assert isinstance(datas, list) and datas, "spec collected no data files"

        text = _SPEC_FILE.read_text(encoding="utf-8")
        assert 'endswith((".md", ".yaml", ".yml", ".typed"))' in text


class TestHandMaintainedRemainder:
    def test_third_party_hidden_imports_resolve(self) -> None:
        """The third-party entries cannot be derived, so check they still exist.

        Replaces the old stale-entry check, which the derivation makes vacuous
        for tapps_mcp modules but which still has teeth here: dropping one of
        these dependencies leaves a hidden import pointing at nothing.
        """
        text = _SPEC_FILE.read_text(encoding="utf-8")
        unresolvable = []
        for name in _THIRD_PARTY:
            assert f'"{name}"' in text, f"{name} is no longer listed in {_SPEC_FILE.name}"
            try:
                found = importlib.util.find_spec(name) is not None
            except (ImportError, ValueError):
                found = False
            if not found:
                unresolvable.append(name)
        assert not unresolvable, (
            f"{len(unresolvable)} third-party hidden import(s) in {_SPEC_FILE.name} "
            f"are not installed: {unresolvable}"
        )
