# Quick test: send initialize + tools/list to container via stdin, count tools in response.
$init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
$tools = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
$input = $init + "`n" + $tools + "`n"
$output = $input | docker run -i --rm tappsmcp:local tapps-mcp serve 2>&1
$count = 0
foreach ($line in ($output -split "`n")) {
    $line = $line.Trim()
    if ($line -eq "") { continue }
    try {
        $j = $line | ConvertFrom-Json
        if ($j.id -eq 2 -and $j.result) {
            $count = $j.result.tools.Count
            break
        }
    } catch {}
}
if ($count -ge 28) { Write-Host "PASS: tapps-mcp returned $count tools (expected >= 28)" } else { Write-Host "FAIL: tapps-mcp returned $count tools"; exit 1 }
