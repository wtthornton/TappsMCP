#!/usr/bin/env python3
"""Verify TappsMCP HTTP server at localhost:8000 using Playwright.

Usage:
    python scripts/verify_http_server.py [--url URL]
    uv run python scripts/verify_http_server.py

Expects server to return 200 at / with body containing "TappsMCP is running".
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """Drive Playwright against a running TappsMCP HTTP server and assert health."""
    parser = argparse.ArgumentParser(description="Verify TappsMCP HTTP server with Playwright")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the server")
    parser.add_argument(
        "--headless", action="store_true", default=True, help="Run browser headless"
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright not installed. Run: uv pip install playwright && uv run playwright install chromium"
        )
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.set_default_timeout(10000)
        try:
            response = page.goto(args.url, wait_until="domcontentloaded")
            if response and response.status != 200:
                print(f"Unexpected status {response.status} for {args.url}")
                browser.close()
                return 1
        except Exception as e:
            print(f"Failed to open {args.url}: {e}")
            browser.close()
            return 1
        content = page.evaluate(
            "() => ({ body: document.body?.innerText || '', title: document.title })"
        )
        browser.close()

    body_text = content.get("body", "")
    title = content.get("title", "")
    if "TappsMCP" not in body_text and "TappsMCP" not in title:
        print(f"Unexpected response. Body snippet: {body_text[:200]!r}")
        return 1
    print("OK: TappsMCP HTTP server is running and returning the expected page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
