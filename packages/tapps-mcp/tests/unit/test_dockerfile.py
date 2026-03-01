"""Coverage alias for dockerfile.py — real tests in test_validators.py."""


def test_dockerfile_importable() -> None:
    from tapps_mcp.validators import dockerfile  # noqa: F401
