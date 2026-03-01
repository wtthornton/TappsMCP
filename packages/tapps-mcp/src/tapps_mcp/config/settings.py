"""TappsMCP configuration system - re-exported from tapps_core.config.settings.

This module re-exports all public symbols for backward compatibility.
The canonical implementation lives in ``tapps_core.config.settings``.
"""

from __future__ import annotations

from tapps_core.config.settings import PRESETS as PRESETS
from tapps_core.config.settings import AdaptiveSettings as AdaptiveSettings
from tapps_core.config.settings import MemoryDecaySettings as MemoryDecaySettings
from tapps_core.config.settings import MemorySettings as MemorySettings
from tapps_core.config.settings import QualityPreset as QualityPreset
from tapps_core.config.settings import ScoringWeights as ScoringWeights
from tapps_core.config.settings import TappsMCPSettings as TappsMCPSettings
from tapps_core.config.settings import _load_yaml_config as _load_yaml_config
from tapps_core.config.settings import _reset_settings_cache as _reset_settings_cache
from tapps_core.config.settings import load_settings as load_settings
