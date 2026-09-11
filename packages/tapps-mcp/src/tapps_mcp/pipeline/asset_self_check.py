"""TAP-7156: fail loudly when an emitted executable asset is malformed.

``install_or_refresh_asset``'s ``migrated`` branch (:mod:`skill_asset_policy`)
used to splice a legacy file's raw body in unwrapped below the managed block,
which could leave an emitted ``.sh``/``.py``/``.js`` asset with more than one
``#!`` line or, for ``.js``, a duplicate top-level declaration that is a real
``SyntaxError``. The fix (comment-wrapping the preserved region) removes the
producer of that state, but nothing previously re-checked the *result* —
a future regression in the same branch, or a hand-edit that reintroduces a
second shebang, would ship silently. This module is that check: run it after
``tapps_upgrade`` writes its executable assets and it exits non-zero, naming
every offending path, instead of leaving the defect to be discovered later
as a broken script in the field.
"""

from __future__ import annotations

import argparse
import py_compile
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import click

_SHEBANG_RE = re.compile(r"^#!", re.MULTILINE)

#: Suffixes this check parses for syntax validity, beyond the shebang count.
_PARSEABLE_SUFFIXES = frozenset({".sh", ".py", ".js"})


@dataclass(frozen=True)
class AssetViolation:
    """One emitted asset that failed the post-upgrade self-check."""

    path: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


def _count_shebangs(content: str) -> int:
    return len(_SHEBANG_RE.findall(content))


def _check_sh_syntax(path: Path) -> str | None:
    bash = shutil.which("bash")
    if bash is None:
        return None
    result = subprocess.run([bash, "-n", str(path)], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return f"bash -n failed: {result.stderr.strip()}"
    return None


def _check_py_syntax(path: Path) -> str | None:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            py_compile.compile(str(path), cfile=str(Path(tmp_dir) / "out.pyc"), doraise=True)
    except py_compile.PyCompileError as exc:
        return f"py_compile failed: {exc}"
    return None


def _check_js_syntax(path: Path) -> str | None:
    node = shutil.which("node")
    if node is None:
        return None
    result = subprocess.run(
        [node, "--check", str(path)], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return f"node --check failed: {result.stderr.strip()}"
    return None


_SYNTAX_CHECKS = {
    ".sh": _check_sh_syntax,
    ".py": _check_py_syntax,
    ".js": _check_js_syntax,
}


def check_asset(path: Path) -> AssetViolation | None:
    """Return the violation for *path*, or ``None`` if it is well-formed.

    Checks two independent things: at most one ``#!`` line anywhere in the
    file (a second shebang is always a defect — the kernel only honors line
    1, so any other occurrence is leftover/duplicated content), and, for a
    suffix this module knows how to parse, that the interpreter's own syntax
    check accepts it.
    """
    content = path.read_text(encoding="utf-8")
    shebang_count = _count_shebangs(content)
    if shebang_count > 1:
        return AssetViolation(path, f"{shebang_count} shebang lines (expected at most 1)")

    suffix = path.suffix.lower()
    checker = _SYNTAX_CHECKS.get(suffix)
    if checker is not None:
        reason = checker(path)
        if reason is not None:
            return AssetViolation(path, reason)
    return None


def check_assets(paths: list[Path]) -> list[AssetViolation]:
    """Run :func:`check_asset` over *paths*, returning every violation found."""
    violations: list[AssetViolation] = []
    for path in paths:
        violation = check_asset(path)
        if violation is not None:
            violations.append(violation)
    return violations


def discover_executable_assets(root: Path) -> list[Path]:
    """Return every tracked-shape executable asset under *root*.

    Scoped to the suffixes the upgrade pipeline actually emits as
    marker-delimited executables (see ``_COMMENT_SYNTAX`` in
    :mod:`skill_asset_policy`) plus ``.mjs`` — a superset walk of the whole
    tree would also flag vendored/third-party scripts this check has no
    business judging.
    """
    suffixes = (*_PARSEABLE_SUFFIXES, ".mjs")
    return sorted(p for suffix in suffixes for p in root.rglob(f"*{suffix}") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Post-upgrade self-check: fail loudly if any emitted executable "
            "asset carries more than one shebang or fails to parse."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Files to check directly, or directories to scan for executable assets.",
    )
    args = parser.parse_args(argv)

    targets: list[Path] = []
    for raw in args.paths:
        if raw.is_dir():
            targets.extend(discover_executable_assets(raw))
        else:
            targets.append(raw)

    violations = check_assets(targets)
    if violations:
        click.echo("tapps upgrade self-check FAILED:", err=True)
        for violation in violations:
            click.echo(f"  {violation}", err=True)
        return 1

    click.echo(f"tapps upgrade self-check OK: {len(targets)} asset(s) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
