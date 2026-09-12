"""Tests for the VAL-04 / VAL-05 static detectors (CB lane L3).

VAL-04 = ``declared-uncalled``: a production constant or function with zero
non-test references. VAL-05 = ``consumed-no-producer``: a dataclass field
read by a non-test consumer but assigned by no non-test producer.

Every fixture here is real Python, imported for real via ``importlib`` with
its cross-file imports actually resolving (proving a green control is not an
import/traceback failure) before the detector is ever pointed at it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tapps_mcp.project.static_detectors import (
    DetectorResult,
    run_consumed_no_producer,
    run_declared_uncalled,
    run_static_detector,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def _write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _import_cleanly(file_path: Path, *sys_path_dirs: Path) -> None:
    """Import ``file_path`` as a real top-level module with ``sys_path_dirs``
    on ``sys.path``, proving the fixture is runnable Python with its
    cross-file imports actually resolving — not a stub whose ImportError
    would masquerade as a detector finding (see the module docstring's
    "ImportError is not a negative control" trap).
    """
    module_name = file_path.stem
    added = [str(d) for d in sys_path_dirs if str(d) not in sys.path]
    sys.path[0:0] = added
    had_module = module_name in sys.modules
    previous = sys.modules.get(module_name)
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        for d in added:
            if d in sys.path:
                sys.path.remove(d)
        if had_module and previous is not None:
            sys.modules[module_name] = previous
        else:
            sys.modules.pop(module_name, None)


def _finding_names(result: DetectorResult) -> set[str]:
    return {f.name for f in result.findings}


class TestDeclaredUncalledConstant:
    """VAL-04 negative/positive controls for the CONTENT_MINIMUM-shaped fixture."""

    def test_constant_read_only_by_tests_is_reported(self, tmp_path: Path) -> None:
        config_src = "CONTENT_MINIMUM = 10\n"
        test_src = (
            "from config import CONTENT_MINIMUM\n\n\n"
            "def test_floor():\n"
            "    assert CONTENT_MINIMUM == 10\n"
        )
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        config_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/config.py", config_src)
        test_path = _write(tmp_path, "packages/tapps-mcp/tests/unit/test_config.py", test_src)
        _import_cleanly(config_path, src_dir)
        _import_cleanly(test_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        constant_findings = [f for f in result.findings if f.kind == "constant"]
        assert "CONTENT_MINIMUM" in {f.name for f in constant_findings}
        finding = next(f for f in constant_findings if f.name == "CONTENT_MINIMUM")
        assert finding.reason == "zero non-test references"
        assert finding.file_path == "packages/tapps-mcp/src/tapps_mcp/config.py"

    def test_constant_with_one_non_test_caller_is_silent(self, tmp_path: Path) -> None:
        config_src = "CONTENT_MINIMUM = 10\n"
        validator_src = (
            "from config import CONTENT_MINIMUM\n\n\n"
            "def check(n):\n"
            "    return n >= CONTENT_MINIMUM\n"
        )
        test_src = (
            "from config import CONTENT_MINIMUM\n\n\n"
            "def test_floor():\n"
            "    assert CONTENT_MINIMUM == 10\n"
        )
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        config_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/config.py", config_src)
        validator_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/validator.py", validator_src
        )
        test_path = _write(tmp_path, "packages/tapps-mcp/tests/unit/test_config.py", test_src)
        _import_cleanly(config_path, src_dir)
        _import_cleanly(validator_path, src_dir)
        _import_cleanly(test_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        assert "CONTENT_MINIMUM" not in _finding_names(result)


class TestDeclaredUncalledFunction:
    """VAL-04 for the top-level-function half of the detector."""

    def test_function_called_only_from_tests_is_reported(self, tmp_path: Path) -> None:
        lib_src = "def legacy_helper():\n    return 42\n"
        test_src = (
            "from lib import legacy_helper\n\n\n"
            "def test_legacy_helper():\n"
            "    assert legacy_helper() == 42\n"
        )
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        lib_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/lib.py", lib_src)
        test_path = _write(tmp_path, "packages/tapps-mcp/tests/unit/test_lib.py", test_src)
        _import_cleanly(lib_path, src_dir)
        _import_cleanly(test_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        function_findings = {f.name for f in result.findings if f.kind == "function"}
        assert "legacy_helper" in function_findings

    def test_function_with_non_test_caller_is_silent(self, tmp_path: Path) -> None:
        lib_src = "def legacy_helper():\n    return 42\n"
        caller_src = "from lib import legacy_helper\n\n\ndef run():\n    return legacy_helper()\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        lib_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/lib.py", lib_src)
        caller_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/caller.py", caller_src)
        _import_cleanly(lib_path, src_dir)
        _import_cleanly(caller_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        assert "legacy_helper" not in {f.name for f in result.findings}


class TestConsumedNoProducer:
    """VAL-05 negative/positive controls for the GTM.channel_mix-shaped fixture."""

    def test_field_read_never_assigned_outside_tests_is_reported(self, tmp_path: Path) -> None:
        models_src = (
            "from dataclasses import dataclass\n\n\n@dataclass\nclass GTM:\n    channel_mix: dict\n"
        )
        renderer_src = "def render(gtm):\n    return gtm.channel_mix\n"
        test_src = (
            "from models import GTM\n\n\n"
            "def test_channel_mix():\n"
            "    gtm = GTM(channel_mix={'paid': 1.0})\n"
            "    assert gtm.channel_mix == {'paid': 1.0}\n"
        )
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        models_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/models.py", models_src)
        renderer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/renderer.py", renderer_src
        )
        test_path = _write(tmp_path, "packages/tapps-mcp/tests/unit/test_models.py", test_src)
        _import_cleanly(models_path, src_dir)
        _import_cleanly(renderer_path, src_dir)
        _import_cleanly(test_path, src_dir)

        result = run_consumed_no_producer(tmp_path)

        assert "GTM.channel_mix" in _finding_names(result)
        finding = next(f for f in result.findings if f.name == "GTM.channel_mix")
        assert finding.reason == "read by a non-test consumer, assigned by no non-test producer"

    def test_field_assigned_in_one_module_and_read_in_another_is_silent(
        self, tmp_path: Path
    ) -> None:
        models_src = (
            "from dataclasses import dataclass\n\n\n@dataclass\nclass GTM:\n    channel_mix: dict\n"
        )
        builder_src = (
            "from models import GTM\n\n\ndef build():\n    return GTM(channel_mix={'paid': 1.0})\n"
        )
        renderer_src = "def render(gtm):\n    return gtm.channel_mix\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        models_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/models.py", models_src)
        builder_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/builder.py", builder_src)
        renderer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/renderer.py", renderer_src
        )
        _import_cleanly(models_path, src_dir)
        _import_cleanly(builder_path, src_dir)
        _import_cleanly(renderer_path, src_dir)

        result = run_consumed_no_producer(tmp_path)

        assert "GTM.channel_mix" not in _finding_names(result)


class TestImportAliasReference:
    """FIX 2a: ``from module import NAME as _NAME`` must register a
    "loaded" reference to the *original* declared name, not just the local
    alias -- the pervasive ``X as _X`` idiom in this codebase was a
    systematic false-positive source before this fix."""

    def test_constant_used_only_via_import_alias_is_silent(self, tmp_path: Path) -> None:
        config_src = "CONTENT_MINIMUM = 10\n"
        consumer_src = (
            "from config import CONTENT_MINIMUM as _CONTENT_MINIMUM\n\n\n"
            "def check(n):\n"
            "    return n >= _CONTENT_MINIMUM\n"
        )
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        config_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/config.py", config_src)
        consumer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/consumer.py", consumer_src
        )
        _import_cleanly(config_path, src_dir)
        _import_cleanly(consumer_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        assert "CONTENT_MINIMUM" not in _finding_names(result)

    def test_star_import_alias_is_skipped_without_crashing(self, tmp_path: Path) -> None:
        config_src = "CONTENT_MINIMUM = 10\n"
        consumer_src = "from config import *\n\n\ndef check(n):\n    return n >= CONTENT_MINIMUM\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        config_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/config.py", config_src)
        consumer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/consumer.py", consumer_src
        )
        _import_cleanly(config_path, src_dir)
        _import_cleanly(consumer_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        assert result.mode == "declared-uncalled"


class TestClickDecoratorDispatch:
    """FIX 2b: a function decorated with the Click ``@group.command(...)``/
    ``@group.group(...)`` registration shape is a framework-mediated entry
    point (Click dispatches it by string lookup at runtime) and must not be
    reported as declared-uncalled, matched by decorator shape rather than a
    name-based allowlist."""

    def test_click_command_decorated_function_is_silent(self, tmp_path: Path) -> None:
        cli_src = (
            "import click\n\n\n"
            "@click.group()\n"
            "def fleet_group():\n"
            "    pass\n\n\n"
            "@fleet_group.command('start')\n"
            "def fleet_start():\n"
            "    return 1\n"
        )
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        cli_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/cli_fleet.py", cli_src)
        _import_cleanly(cli_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        assert "fleet_start" not in {f.name for f in result.findings if f.kind == "function"}

    def test_plain_function_with_no_callers_is_still_reported(self, tmp_path: Path) -> None:
        cli_src = "def orphan_helper():\n    return 1\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        cli_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/cli_fleet.py", cli_src)
        _import_cleanly(cli_path, src_dir)

        result = run_declared_uncalled(tmp_path)

        assert "orphan_helper" in {f.name for f in result.findings if f.kind == "function"}


class TestTypeCheckingGuardedProducer:
    """FIX 3: a dataclass field assigned only inside ``if TYPE_CHECKING:``
    has no real producer (that code never runs), so it must be flagged --
    the pre-fix detector silently credited it as having a legitimate
    producer, clearing a genuine VAL-05 defect with no visible signal."""

    def test_field_assigned_only_under_type_checking_is_reported(self, tmp_path: Path) -> None:
        models_src = (
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n"
            "from typing import TYPE_CHECKING\n\n\n"
            "@dataclass\n"
            "class Widget:\n"
            "    label: str\n\n\n"
            "if TYPE_CHECKING:\n"
            "    _w = Widget(label='x')\n"
            "    _w.label = 'unreachable-at-runtime'\n"
        )
        consumer_src = "def show(w):\n    return w.label\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        models_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/models.py", models_src)
        consumer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/consumer.py", consumer_src
        )
        _import_cleanly(models_path, src_dir)
        _import_cleanly(consumer_path, src_dir)

        result = run_consumed_no_producer(tmp_path)

        assert "Widget.label" in _finding_names(result)

    def test_field_assigned_in_type_checking_else_branch_is_silent(self, tmp_path: Path) -> None:
        models_src = (
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n"
            "from typing import TYPE_CHECKING\n\n\n"
            "@dataclass\n"
            "class Widget:\n"
            "    label: str\n\n\n"
            "if TYPE_CHECKING:\n"
            "    pass\n"
            "else:\n"
            "    _w = Widget(label='x')\n"
            "    _w.label = 'runs-at-runtime'\n"
        )
        consumer_src = "def show(w):\n    return w.label\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        models_path = _write(tmp_path, "packages/tapps-mcp/src/tapps_mcp/models.py", models_src)
        consumer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/consumer.py", consumer_src
        )
        _import_cleanly(models_path, src_dir)
        _import_cleanly(consumer_path, src_dir)

        result = run_consumed_no_producer(tmp_path)

        assert "Widget.label" not in _finding_names(result)


class TestSetattrProducer:
    """FIX 3 (setattr control): a string-literal ``setattr(obj, "field", v)``
    is a genuine, statically recognisable producer."""

    def test_field_produced_only_via_setattr_is_silent(self, tmp_path: Path) -> None:
        models_src = (
            "from dataclasses import dataclass\n\n\n@dataclass\nclass Widget:\n    label: str\n"
        )
        builder_src = (
            "from models_setattr import Widget\n\n\n"
            "def build():\n"
            "    w = Widget('placeholder')\n"  # positional: no kwarg producer
            "    setattr(w, 'label', 'assigned-via-setattr')\n"
            "    return w\n"
        )
        renderer_src = "def render(w):\n    return w.label\n"
        src_dir = tmp_path / "packages/tapps-mcp/src/tapps_mcp"
        models_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/models_setattr.py", models_src
        )
        builder_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/builder_setattr.py", builder_src
        )
        renderer_path = _write(
            tmp_path, "packages/tapps-mcp/src/tapps_mcp/renderer_setattr.py", renderer_src
        )
        _import_cleanly(models_path, src_dir)
        _import_cleanly(builder_path, src_dir)
        _import_cleanly(renderer_path, src_dir)

        result = run_consumed_no_producer(tmp_path)

        assert "Widget.label" not in _finding_names(result)


class TestRunStaticDetectorDispatch:
    def test_invalid_mode_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="mode must be one of"):
            run_static_detector("not-a-real-mode", tmp_path)

    def test_dispatches_declared_uncalled(self, tmp_path: Path) -> None:
        result = run_static_detector("declared-uncalled", tmp_path)
        assert result.mode == "declared-uncalled"

    def test_dispatches_consumed_no_producer(self, tmp_path: Path) -> None:
        result = run_static_detector("consumed-no-producer", tmp_path)
        assert result.mode == "consumed-no-producer"


class TestFireRateOnRealPackage:
    """Fire rate over the real package — recall on a planted fixture proves
    nothing about precision (second trap); this measures the real rate."""

    def test_declared_uncalled_fire_rate_is_not_unconditional(self) -> None:
        result = run_declared_uncalled(REPO_ROOT)
        assert result.examined > 100
        assert 0.0 < result.fire_rate < 0.5

    def test_consumed_no_producer_fire_rate_is_not_unconditional(self) -> None:
        result = run_consumed_no_producer(REPO_ROOT)
        assert result.examined > 20
        assert 0.0 <= result.fire_rate < 0.5
