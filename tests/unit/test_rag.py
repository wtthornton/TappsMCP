"""Coverage alias for rag.py — real tests in test_expert_rag.py."""


def test_rag_importable() -> None:
    from tapps_mcp.experts import rag  # noqa: F401
