#!/usr/bin/env python3
"""Quick validation of Epic 15 dependency scan integration."""

from __future__ import annotations

import asyncio
import json
import os

# Set project root
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from tapps_mcp.config.settings import load_settings
    from tapps_mcp.server import tapps_dependency_scan
    from tapps_mcp.server_pipeline_tools import tapps_session_start, tapps_validate_changed

    settings = load_settings()
    root = str(settings.project_root)
    print(f"Project root: {root}\n")

    # 1. tapps_session_start (includes dependency scan)
    print("=== tapps_session_start ===")
    sess = tapps_session_start(project_root=root)
    dep = sess.get("data", {}).get("dependency_scan", {})
    if dep:
        print(f"  dependency_scan: {json.dumps(dep, indent=2)}")
    else:
        print("  (no dependency_scan in response)")
    print()

    # 2. tapps_dependency_scan
    print("=== tapps_dependency_scan ===")
    scan = await tapps_dependency_scan(project_root=root)
    data = scan.get("data", {})
    print(f"  success: {scan.get('success')}")
    print(f"  scanned_packages: {data.get('scanned_packages')}")
    print(f"  total_findings: {data.get('total_findings')}")
    print(f"  structuredContent: {'yes' if 'structuredContent' in scan else 'no'}")
    if data.get("error"):
        print(f"  error: {data['error']}")
    print()

    # 3. tapps_validate_changed (includes dependency scan)
    print("=== tapps_validate_changed ===")
    val = await tapps_validate_changed(file_paths="", include_security=True)
    data = val.get("data", {})
    print(f"  success: {val.get('success')}")
    print(f"  all_gates_passed: {data.get('all_gates_passed')}")
    dep = data.get("dependency_scan", {})
    if dep:
        print(f"  dependency_scan: {json.dumps(dep, indent=2)}")
    else:
        print("  (no dependency_scan in response)")
    print("  summary:", data.get("summary", "")[:80] + "...")


if __name__ == "__main__":
    asyncio.run(main())
