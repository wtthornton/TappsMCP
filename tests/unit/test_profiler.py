"""Coverage alias for profiler.py — real tests in test_project_profile.py."""


def test_profiler_importable() -> None:
    from tapps_mcp.project import profiler  # noqa: F401
