"""Fixture module sharing a basename with pkg_a/utils.py (ambiguity test)."""

from pkg_a.calc import add


def helper_b():
    return add(1, 2)
