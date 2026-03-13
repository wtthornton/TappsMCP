"""Common utilities shared across TappsMCP modules.

Re-exports from tapps_core.common for backward compatibility.
"""

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
    WriteMode,
    detect_write_mode,
)

__all__ = [
    "AgentInstructions",
    "FileManifest",
    "FileOperation",
    "WriteMode",
    "detect_write_mode",
]
