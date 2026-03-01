"""Backward-compatible re-export."""
from __future__ import annotations

from tapps_core.knowledge.library_detector import (
    _clean_package_name as _clean_package_name,
)
from tapps_core.knowledge.library_detector import (
    _parse_package_json as _parse_package_json,
)
from tapps_core.knowledge.library_detector import _parse_pyproject as _parse_pyproject
from tapps_core.knowledge.library_detector import (
    _parse_requirements as _parse_requirements,
)
from tapps_core.knowledge.library_detector import detect_libraries as detect_libraries
