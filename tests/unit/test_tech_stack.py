"""Coverage alias for tech_stack.py — real tests in test_project_profile.py."""


def test_tech_stack_importable() -> None:
    from tapps_mcp.project import tech_stack  # noqa: F401
