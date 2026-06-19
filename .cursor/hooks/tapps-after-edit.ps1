# tapps-mcp-hook-version: 3.12.43
# tapps-mcp-hook-content-sha: 1b1eb9ca
# TappsMCP afterFileEdit hook (fire-and-forget) — TAP-1330 import parity
# Detects external imports requiring tapps_lookup_docs. Advisory only.
$rawInput = @($input) -join "`n"
$env:TAPPS_HOOK_INPUT = $rawInput
$py = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
$file = "unknown"
$libs = ""
if ($py) {
    $parseScript = @'
import os, json, re
from pathlib import Path

try:
    d = json.loads(os.environ.get("TAPPS_HOOK_INPUT", "{}"))
    ti = d.get("tool_input") or d.get("toolInput") or {}
    f = (
        d.get("file")
        or d.get("file_path")
        or ti.get("file_path")
        or ti.get("path")
        or ""
    )
    content = ti.get("content") or ti.get("new_string") or ""
    if not content and f:
        candidate = Path(f)
        if not candidate.is_file():
            for root in (
                os.environ.get("TAPPS_MCP_PROJECT_ROOT"),
                os.environ.get("TAPPS_PROJECT_ROOT"),
                os.environ.get("CURSOR_PROJECT_DIR"),
                os.getcwd(),
            ):
                if not root:
                    continue
                alt = Path(root) / f
                if alt.is_file():
                    candidate = alt
                    break
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8", errors="replace")
    print(f)
    libs: set[str] = set()
    if f.endswith((".py", ".pyi")):
        for m in re.finditer(
            r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.M
        ):
            libs.add(m.group(1))
    elif f.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")):
        js_import = r"^\s*import[^'"]*['"]([^'"./][^'"]*)['"]"
        for m in re.finditer(js_import, content, re.M):
            libs.add(m.group(1).split("/")[0])
    print(",".join(sorted(libs)))
except Exception:
    print("")
    print("")
'@
    $parsed = @($parseScript | & $py.Source - 2>$null)
    if ($parsed.Count -ge 1) { $file = [string]$parsed[0] }
    if ($parsed.Count -ge 2) { $libs = [string]$parsed[1] }
}
switch -Regex ($file) {
    '\.(py|pyi|ts|tsx|js|jsx|go|rs)$' {
        Write-Output "Edited: $file — run tapps_quick_check after this edit."
        if ($libs) {
            [Console]::Error.WriteLine(
                "Imports detected ($libs) — call tapps_lookup_docs(library=..., topic=...) before using those APIs in this session (TAP-1330)."
            )
        }
    }
    default {
        if ($file -and $file -ne "unknown") {
            Write-Output "File edited: $file"
            Write-Output "Consider running tapps_quick_check to verify quality."
        }
    }
}
exit 0
