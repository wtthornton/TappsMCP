"""Naming-site and slot-validation tests for handoffs (TAP-6870).

``handoff_path`` is the single site that names a handoff file, and
``handoff_memory_key`` the single site that names its brain row. Everything
here pins one of three properties: the no-slot path is byte-identical to the
pre-change constant, a slot lands under ``handoffs/``, and an invalid slot is
refused by *both* defences before any path is written.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tapps_mcp.tools.handoff_schema import (
    SESSION_HANDOFF_MEMORY_KEY,
    InvalidHandoffSlotError,
    handoff_memory_key,
    handoff_path,
)

# The literal this module replaced. Written out rather than imported so the
# test still fails if the naming site silently changes what it returns.
_PRE_CHANGE_RELATIVE = Path(".tapps-mcp") / "session-handoff.md"

_HANDOFF_BASENAME = "session-handoff.md"
_HANDOFF_DIR = ".tapps-mcp"
_PATH_CONSTRUCTORS = frozenset({"Path", "PurePath", "PurePosixPath", "PosixPath"})


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """Identity of every docstring node, so a prose mention is not a usage.

    Comments never reach the AST at all; docstrings do, as the first statement
    of a module, function or class. Excluding them by identity is what lets the
    check pass on a module that merely *names* the file (VAL-7's legitimate
    mention control) while still firing on one that composes it.
    """
    scopes = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, scopes):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            ids.add(id(first.value))
    return ids


def _fold_constant(node: ast.Constant, skip: set[int]) -> str | None:
    if id(node) in skip or not isinstance(node.value, str):
        return None
    return node.value


def _fold_fstring(node: ast.JoinedStr, skip: set[int]) -> str | None:
    parts: list[str] = []
    for value in node.values:
        folded = _fold_literal_path(value, skip)
        if folded is None:
            return None
        parts.append(folded)
    return "".join(parts)


def _fold_binop(node: ast.BinOp, skip: set[int]) -> str | None:
    left = _fold_literal_path(node.left, skip)
    right = _fold_literal_path(node.right, skip)
    if isinstance(node.op, ast.Add):
        return None if left is None or right is None else left + right
    if isinstance(node.op, ast.Div):
        return _join([left, right])
    return None


def _fold_call(node: ast.Call, skip: set[int]) -> str | None:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name not in _PATH_CONSTRUCTORS:
        return None
    return _join([_fold_literal_path(arg, skip) for arg in node.args])


def _join(segments: list[str | None]) -> str | None:
    """Join the literal segments of a path composition, dropping the rest.

    A non-literal operand (a variable such as ``root``) contributes nothing,
    which is what lets ``root / ".tapps-mcp" / "x.md"`` fold to
    ``.tapps-mcp/x.md``.
    """
    return "/".join(s for s in segments if s) or None


def _fold_literal_path(node: ast.AST, skip: set[int]) -> str | None:
    """Constant-fold a path-composition expression to its literal segments.

    Returns the ``/``-joined literal fragments the expression builds, or None
    when nothing about it is literal. This is why the check sees
    ``Path(".tapps-mcp") / ("session-" + "handoff.md")``, which no substring
    scan can: the fold reassembles a name the source never spells out.
    """
    if isinstance(node, ast.Constant):
        return _fold_constant(node, skip)
    if isinstance(node, ast.JoinedStr):
        return _fold_fstring(node, skip)
    if isinstance(node, ast.BinOp):
        return _fold_binop(node, skip)
    if isinstance(node, ast.Call):
        return _fold_call(node, skip)
    return None


def _rebuilds_a_handoff_name(folded: str) -> bool:
    segments = re.split(r"[/\\]", folded)
    if _HANDOFF_BASENAME in segments or folded.endswith(_HANDOFF_BASENAME):
        return True
    return _HANDOFF_DIR in segments and "handoffs" in segments


def composed_handoff_literals(source: str, filename: str) -> list[str]:
    """Every expression in ``source`` that rebuilds a handoff path from parts.

    A usage-shape check, not a substring count: it walks expressions rather
    than characters, so a docstring or comment naming the file is invisible to
    it and a literal split across a concatenation is not.
    """
    tree = ast.parse(source, filename)
    skip = _docstring_constant_ids(tree)
    found: list[str] = []

    def visit(node: ast.AST) -> None:
        folded = _fold_literal_path(node, skip)
        if folded is not None and _rebuilds_a_handoff_name(folded):
            # Report the outermost composition only; its operands are the
            # same finding seen from further in.
            found.append(f"{filename}:{getattr(node, 'lineno', '?')}: {ast.unparse(node)}")
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return found


def function_calls_callee(source: str, filename: str, function: str, callee: str) -> bool:
    """True when ``function`` in ``source`` contains a call to ``callee``."""
    tree = ast.parse(source, filename)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or node.name != function:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if (isinstance(func, ast.Name) and func.id == callee) or (
                isinstance(func, ast.Attribute) and func.attr == callee
            ):
                return True
    return False


def imports_from(source: str, filename: str, module: str, name: str) -> bool:
    """True when ``source`` imports ``name`` from ``module``.

    Pairs with :func:`function_calls_callee`: a call to something *named*
    ``handoff_path`` proves nothing if the module defines its own.
    """
    tree = ast.parse(source, filename)
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == module
        and any(alias.name == name for alias in node.names)
        for node in ast.walk(tree)
    )


# --- VAL-7 fixtures: the mutations the check must catch, and the one it must not.

# The exact surviving mutation the adversarial verifier planted: the import is
# gone and the literal is composed inline inside the resolving function.
_MUTANT_INLINE = """
from pathlib import Path

def audit_project_root(root):
    handoff_file = root / Path(".tapps-mcp") / "session-handoff.md"
    return {"path": str(handoff_file.relative_to(root))}
"""

# The shape the spec names as the one substring counting misses: the basename
# never appears contiguously in the source.
_MUTANT_SPLIT_LITERAL = """
from pathlib import Path

def audit_project_root(root):
    return root / Path(".tapps-mcp") / ("session-" + "handoff.md")
"""

_MUTANT_SINGLE_ARG = """
from pathlib import Path

def audit_project_root(root):
    return root / Path(".tapps-mcp/session-handoff.md")
"""

_MUTANT_FSTRING = """
def audit_project_root(root):
    return root / ".tapps-mcp" / f"session-handoff.md"
"""

# The legitimate mention: prose names the file in a module docstring, a
# function docstring and a comment, but the only resolution is the naming site.
_LEGITIMATE_MENTION = '''
"""Audit helpers that read .tapps-mcp/session-handoff.md."""

from tapps_mcp.tools.handoff_schema import handoff_path

def audit_project_root(root):
    """Resolve session-handoff.md for this project root."""
    # Defaults to .tapps-mcp/session-handoff.md when no slot is passed.
    return handoff_path(root)
'''


class TestDefaultPathUnchanged:
    def test_no_slot_returns_pre_change_path(self, tmp_path: Path) -> None:
        assert handoff_path(tmp_path) == tmp_path / _PRE_CHANGE_RELATIVE

    def test_no_slot_string_is_byte_identical(self, tmp_path: Path) -> None:
        assert str(handoff_path(tmp_path)) == str(tmp_path / ".tapps-mcp" / "session-handoff.md")

    def test_slot_none_is_the_default(self, tmp_path: Path) -> None:
        assert handoff_path(tmp_path, None) == handoff_path(tmp_path)

    def test_no_slot_brain_key_unchanged(self) -> None:
        assert handoff_memory_key() == "session-handoff"
        assert handoff_memory_key() == SESSION_HANDOFF_MEMORY_KEY


class TestSlottedPath:
    def test_slot_lands_under_handoffs_dir(self, tmp_path: Path) -> None:
        assert handoff_path(tmp_path, "ceg-hub") == (
            tmp_path / ".tapps-mcp" / "handoffs" / "ceg-hub.md"
        )

    def test_slot_brain_key_is_namespaced(self) -> None:
        # A dot, not a colon: the brain's key slug pattern excludes ``:``, so the
        # colon form was unwritable (TAP-6873). The string is pinned here; that
        # the brain actually accepts it is proved by a real save in
        # ``test_handoff_brain_key.py`` — this assertion alone cannot show it.
        assert handoff_memory_key("ceg-hub") == "session-handoff.ceg-hub"

    @pytest.mark.parametrize("slot", ["a", "0", "handoff-slots", "a" * 48])
    def test_allowlist_accepts_legal_slots(self, tmp_path: Path, slot: str) -> None:
        assert handoff_path(tmp_path, slot).name == f"{slot}.md"

    def test_the_length_boundary_is_between_48_and_49(self, tmp_path: Path) -> None:
        # Pins both sides of ``{0,47}`` in one place: widening it to {0,48}
        # keeps the 48 case green and only this assertion notices.
        assert handoff_path(tmp_path, "a" * 48).name == f"{'a' * 48}.md"
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(tmp_path, "a" * 49)
        assert exc.value.envelope["extra"]["reason"] == "failed_allowlist"


class TestSlotValidationRejects:
    # The four cases the spec names, plus the shapes the regex exists to stop.
    @pytest.mark.parametrize(
        "slot",
        [
            "../escape",
            "a/b",
            "",
            "a" * 64,
            "a" * 49,  # boundary: 48 is the last legal length, 49 the first illegal one
            "..",
            ".hidden",
            "Upper",
            "-leading-dash",
            "has space",
            "trailing.md",
        ],
    )
    def test_invalid_slot_raises(self, tmp_path: Path, slot: str) -> None:
        with pytest.raises(InvalidHandoffSlotError):
            handoff_path(tmp_path, slot)

    def test_error_carries_a_structured_envelope(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(tmp_path, "../escape")
        envelope = exc.value.envelope
        assert envelope["ok"] is False
        assert envelope["code"] == "invalid_handoff_slot"
        assert envelope["gate"] == "handoff_slot_validation"
        assert envelope["hint"]
        assert envelope["extra"]["slot"] == "../escape"

    def test_invalid_slot_never_touches_the_filesystem(self, tmp_path: Path) -> None:
        before = sorted(p.name for p in tmp_path.iterdir())
        for slot in ("../escape", "a/b", "", "a" * 64):
            with pytest.raises(InvalidHandoffSlotError):
                handoff_path(tmp_path, slot)
        assert sorted(p.name for p in tmp_path.iterdir()) == before

    def test_memory_key_rejects_the_same_slots(self) -> None:
        for slot in ("../escape", "a/b", "", "a" * 64):
            with pytest.raises(InvalidHandoffSlotError):
                handoff_memory_key(slot)


class TestContainmentIsIndependentOfTheRegex:
    """The post-join check must still hold when the allowlist is bypassed."""

    def test_symlinked_handoffs_dir_pointing_outside_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        (root / ".tapps-mcp").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / ".tapps-mcp" / "handoffs").symlink_to(outside)

        # "legit" passes the allowlist regex; only the containment check sees
        # that the directory it would land in resolves outside the project.
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(root, "legit")
        assert exc.value.envelope["extra"]["reason"] == "escapes_project_root"

    def test_symlinked_handoff_file_pointing_outside_is_rejected(self, tmp_path: Path) -> None:
        # The directory is a real directory here; only the slot's own .md file
        # is a symlink out of the repo. Nothing but resolving the candidate
        # itself can see this.
        root = tmp_path / "proj"
        (root / ".tapps-mcp" / "handoffs").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "legit.md").write_text("stolen", encoding="utf-8")
        (root / ".tapps-mcp" / "handoffs" / "legit.md").symlink_to(outside / "legit.md")

        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(root, "legit")
        assert exc.value.envelope["extra"]["reason"] == "escapes_project_root"

    def test_symlinked_handoff_file_inside_the_slot_dir_is_allowed(self, tmp_path: Path) -> None:
        # Negative control for the case above: a symlinked file whose target
        # stays inside handoffs/ is fine, so the rejection is about escape and
        # not about symlinks as such.
        root = tmp_path / "proj"
        slot_dir = root / ".tapps-mcp" / "handoffs"
        slot_dir.mkdir(parents=True)
        (slot_dir / "real.md").write_text("mine", encoding="utf-8")
        (slot_dir / "legit.md").symlink_to(slot_dir / "real.md")
        assert handoff_path(root, "legit").name == "legit.md"

    def test_symlinked_handoffs_dir_inside_the_project_is_allowed(self, tmp_path: Path) -> None:
        # Negative control: the check rejects *escape*, not symlinks as such.
        root = tmp_path / "proj"
        (root / ".tapps-mcp").mkdir(parents=True)
        inside = root / "elsewhere"
        inside.mkdir()
        (root / ".tapps-mcp" / "handoffs").symlink_to(inside)
        assert handoff_path(root, "legit").name == "legit.md"

    def test_containment_catches_traversal_when_the_regex_is_loosened(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate a future maintainer widening the allowlist: the second
        # defence must still refuse a slot that walks out of handoffs/.
        import re

        from tapps_mcp.tools import handoff_schema

        monkeypatch.setattr(handoff_schema, "_SLOT_RE", re.compile(r"^.*$"))
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(tmp_path, "../escape")
        assert exc.value.envelope["extra"]["reason"] == "escapes_slot_dir"


def _fleet_audit_source() -> tuple[str, str]:
    """Source of the fleet_audit module as actually imported.

    Read through ``__file__`` rather than a path built here, so the check
    cannot be satisfied by a scratch copy that is not the module under test.
    """
    from tapps_mcp.tools import fleet_audit

    path = Path(fleet_audit.__file__)
    return path.read_text(encoding="utf-8"), path.name


class TestTheUsageShapeCheckCanFail:
    """VAL-7's controls. A check never shown to fail has proved nothing.

    These run the check against planted mutations and against a module whose
    only reference is prose, so its verdict on the real tree means something.
    """

    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("inline", _MUTANT_INLINE),
            ("split_literal", _MUTANT_SPLIT_LITERAL),
            ("single_arg", _MUTANT_SINGLE_ARG),
            ("fstring", _MUTANT_FSTRING),
        ],
    )
    def test_true_positive_composition_is_caught(self, label: str, source: str) -> None:
        assert composed_handoff_literals(source, f"mutant_{label}.py")

    def test_true_positive_lost_call_is_caught(self) -> None:
        assert not function_calls_callee(
            _MUTANT_INLINE, "mutant_inline.py", "audit_project_root", "handoff_path"
        )

    def test_legitimate_mention_passes(self) -> None:
        # Prose in a docstring and a comment is not a usage.
        assert composed_handoff_literals(_LEGITIMATE_MENTION, "legit.py") == []
        assert function_calls_callee(
            _LEGITIMATE_MENTION, "legit.py", "audit_project_root", "handoff_path"
        )

    def test_the_check_is_not_a_substring_scan(self) -> None:
        # Both halves of why the spec forbids substring counting: it fires on
        # the mention that is fine, and misses the composition that is not.
        assert _HANDOFF_BASENAME in _LEGITIMATE_MENTION
        assert _HANDOFF_BASENAME not in _MUTANT_SPLIT_LITERAL


class TestNoRestatedConstantSurvives:
    """VAL-7: the other sites resolve a handoff path via the naming site."""

    def test_fleet_audit_reports_the_naming_site_path(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from tapps_mcp.tools import fleet_audit

        (tmp_path / ".tapps-mcp.yaml").write_text("", encoding="utf-8")
        report = fleet_audit.audit_project_root(
            tmp_path,
            since=datetime(2000, 1, 1, tzinfo=UTC),
            include_brain=False,
        )
        expected = handoff_path(tmp_path).relative_to(tmp_path)
        assert report["handoff"]["path"] == str(expected)

    def test_fleet_audit_resolves_by_calling_the_naming_site(self) -> None:
        source, name = _fleet_audit_source()
        assert imports_from(source, name, "tapps_mcp.tools.handoff_schema", "handoff_path")
        assert function_calls_callee(source, name, "audit_project_root", "handoff_path")

    def test_fleet_audit_composes_no_handoff_literal(self) -> None:
        source, name = _fleet_audit_source()
        assert composed_handoff_literals(source, name) == []

    def test_dashboard_constant_has_not_diverged(self, tmp_path: Path) -> None:
        # tapps-core cannot import tapps-mcp (dependency runs the other way),
        # so dashboard.py keeps its own constant and this check fails loudly
        # if the two ever disagree.
        from tapps_core.metrics import dashboard

        assert handoff_path(tmp_path).relative_to(tmp_path) == dashboard._HANDOFF_RELATIVE
