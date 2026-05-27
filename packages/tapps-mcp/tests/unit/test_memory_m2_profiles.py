"""Tests for Epic M2: Memory profile & lifecycle management — non-deprecated pieces.

TAP-1993/TAP-1994: profile_info, profile_list, profile_switch, and reinforce
actions are now refused (delegated to mcp__tapps-brain__brain_status or
brain_remember). Those test classes have been removed.

TestMemorySettingsProfile covers the MemorySettings.profile Pydantic field,
which is still active and not part of the deprecated tool surface.
"""

from __future__ import annotations


class TestMemorySettingsProfile:
    """Tests for the profile field in MemorySettings (TAP-M2)."""

    def test_default_profile_empty(self) -> None:
        from tapps_core.config.settings import MemorySettings

        settings = MemorySettings()
        assert settings.profile == ""

    def test_profile_override(self) -> None:
        from tapps_core.config.settings import MemorySettings

        settings = MemorySettings(profile="research-knowledge")
        assert settings.profile == "research-knowledge"
