"""Exception hierarchy - re-exported from tapps_core.common.exceptions.

This module re-exports all public symbols for backward compatibility.
The canonical implementation lives in ``tapps_core.common.exceptions``.
"""

from __future__ import annotations

from tapps_core.common.exceptions import ConfigurationError as ConfigurationError
from tapps_core.common.exceptions import FileOperationError as FileOperationError
from tapps_core.common.exceptions import PathValidationError as PathValidationError
from tapps_core.common.exceptions import QualityGateError as QualityGateError
from tapps_core.common.exceptions import SecurityError as SecurityError
from tapps_core.common.exceptions import TappsMCPError as TappsMCPError
from tapps_core.common.exceptions import ToolExecutionError as ToolExecutionError
from tapps_core.common.exceptions import ToolNotFoundError as ToolNotFoundError
