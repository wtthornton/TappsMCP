"""Performance smoke test for the interactive viewer's JS particle layer (TAP-1039).

Renders a 50-edge dependency diagram with ``motion="particles"`` in headless
Chromium via ``playwright`` and asserts that the page sustains > 30 fps for
~5 seconds. The test is gated on ``playwright`` being importable AND on the
Chromium browser being installed locally — otherwise it ``skip``s.

Marked ``slow`` so the default test run does not pull it in.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# Skip the entire module when playwright is not installed.
playwright = pytest.importorskip("playwright.async_api")


_FPS_FLOOR: float = 30.0
_SOAK_SECONDS: float = 5.0


def _make_50_edge_diagram() -> tuple[str, list[tuple[str, str]]]:
    """Return a (title, [(label, mermaid_content)]) tuple with 50 edges."""
    nodes = [f"N{i}" for i in range(51)]
    edges_md = "\n".join(f"  {nodes[i]} --> {nodes[i + 1]}" for i in range(50))
    mermaid_src = f"graph LR\n{edges_md}\n"
    return ("Dependency Graph", [("Dependency Graph", mermaid_src)])


_FPS_MEASURE_JS = """
async () => {
    return new Promise((resolve) => {
        let frames = 0;
        const start = performance.now();
        function tick() {
            frames++;
            const elapsed = performance.now() - start;
            if (elapsed >= """ + str(int(_SOAK_SECONDS * 1000)) + """) {
                resolve(frames / (elapsed / 1000));
                return;
            }
            requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    });
}
"""


@pytest.mark.asyncio
async def test_50_edge_diagram_sustains_30fps_with_particles() -> None:
    """Headless Chromium fps smoke test for the particle layer.

    Skips if Chromium is not installed locally (``playwright install``
    has not been run). Asserts > 30 fps over a 5-second sample.
    """
    from playwright.async_api import async_playwright

    from docs_mcp.generators.interactive_html import InteractiveHtmlGenerator

    page_title, diagrams = _make_50_edge_diagram()
    gen = InteractiveHtmlGenerator()
    result = gen.generate(
        diagrams,
        title=page_title,
        motion="particles",
        diagram_types=["dependency"],
    )

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium not installed for playwright: {exc}")

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                reduced_motion="no-preference",
            )
            page = await context.new_page()
            await page.set_content(result.content, wait_until="networkidle")
            # Give Mermaid a moment to render the SVG.
            await page.wait_for_selector(".diagram-wrapper svg", timeout=15_000)
            # Let the particle layer settle.
            await asyncio.sleep(0.5)
            fps = await page.evaluate(_FPS_MEASURE_JS)
        finally:
            await browser.close()

    assert isinstance(fps, (int, float))
    assert fps > _FPS_FLOOR, f"FPS {fps:.1f} below floor {_FPS_FLOOR}"
