"""Tests for DockerSettings model in tapps_core.config.settings."""

from __future__ import annotations

from tapps_core.config.settings import DockerSettings, TappsMCPSettings


class TestDockerSettingsDefaults:
    """Verify DockerSettings field defaults."""

    def test_default_enabled(self) -> None:
        ds = DockerSettings()
        assert ds.enabled is False

    def test_default_transport(self) -> None:
        ds = DockerSettings()
        assert ds.transport == "auto"

    def test_default_profile(self) -> None:
        ds = DockerSettings()
        assert ds.profile == "tapps-standard"

    def test_default_image(self) -> None:
        ds = DockerSettings()
        assert ds.image == "ghcr.io/wtthornton/tapps-mcp:latest"

    def test_default_docs_image(self) -> None:
        ds = DockerSettings()
        assert ds.docs_image == "ghcr.io/wtthornton/docs-mcp:latest"

    def test_default_companions(self) -> None:
        ds = DockerSettings()
        assert ds.companions == ["context7"]


class TestDockerSettingsCustom:
    """Verify DockerSettings with custom values."""

    def test_custom_values(self) -> None:
        ds = DockerSettings(
            enabled=True,
            transport="docker",
            profile="my-profile",
            image="myregistry/tapps:v1",
            docs_image="myregistry/docs:v1",
            companions=["context7", "github"],
        )
        assert ds.enabled is True
        assert ds.transport == "docker"
        assert ds.profile == "my-profile"
        assert ds.image == "myregistry/tapps:v1"
        assert ds.docs_image == "myregistry/docs:v1"
        assert ds.companions == ["context7", "github"]

    def test_empty_companions(self) -> None:
        ds = DockerSettings(companions=[])
        assert ds.companions == []


class TestDockerSettingsSerialization:
    """Verify DockerSettings serialization round-trip."""

    def test_model_dump(self) -> None:
        ds = DockerSettings(enabled=True, transport="docker")
        data = ds.model_dump()
        assert data["enabled"] is True
        assert data["transport"] == "docker"
        assert "profile" in data
        assert "image" in data
        assert "companions" in data

    def test_model_validate(self) -> None:
        data = {
            "enabled": True,
            "transport": "exe",
            "profile": "custom",
            "image": "img:latest",
            "docs_image": "docs:latest",
            "companions": ["a", "b"],
        }
        ds = DockerSettings.model_validate(data)
        assert ds.enabled is True
        assert ds.transport == "exe"
        assert ds.companions == ["a", "b"]


class TestTappsMCPSettingsDockerField:
    """Verify DockerSettings is embedded in TappsMCPSettings."""

    def test_default_docker_field(self, tmp_path: object) -> None:
        settings = TappsMCPSettings()
        assert isinstance(settings.docker, DockerSettings)
        assert settings.docker.enabled is False

    def test_docker_from_dict(self) -> None:
        settings = TappsMCPSettings(
            docker={"enabled": True, "transport": "docker"},  # type: ignore[arg-type]
        )
        assert settings.docker.enabled is True
        assert settings.docker.transport == "docker"
