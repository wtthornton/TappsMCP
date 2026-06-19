# tapps-mcp-hook-version: 3.12.43
# tapps-mcp-hook-content-sha: 7ff6aef8
# TappsMCP Cursor stop hook — TAP-3918 loop-metrics + optional followup
$rawInput = @($input) -join "`n"
$tapps = Get-Command tapps-mcp -ErrorAction SilentlyContinue
if (-not $tapps) { exit 0 }
try {
    $out = $rawInput | & tapps-mcp loop-metrics-record 2>$null
    if ($out) { Write-Output $out }
} catch {}
exit 0
