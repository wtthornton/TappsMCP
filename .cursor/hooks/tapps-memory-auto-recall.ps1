# TappsMCP Memory Auto-Recall (Cursor — Epic 65.4)
$rawInput = @($input) -join "`n"
$defaultQuery = "project context architecture"
$query = $defaultQuery
$projDir = "."
try {
    $data = $rawInput | ConvertFrom-Json
    $query = if ($data.prompt) { $data.prompt }
             elseif ($data.last_user_message) { $data.last_user_message }
             elseif ($data.last_message) { $data.last_message }
             elseif ($data.context) { $data.context }
             else { $defaultQuery }
    if ($data.workspace_roots -and $data.workspace_roots.Count -gt 0) {
        $projDir = $data.workspace_roots[0]
    } elseif ($data.cwd) {
        $projDir = $data.cwd
    }
    if ($data.messages -and $data.messages.Count -gt 0) {
        $last = $data.messages[-1]
        $c = if ($last.content) { $last.content } elseif ($last.text) { $last.text } else { "" }
        if ($c) { $query = $c }
    }
    $query = ($query -as [string] -or "").Substring(0, [Math]::Min(500, ($query -as [string]).Length))
} catch {}
if ($query -ne $defaultQuery -and $query.Length -lt 50) {
    exit 0
}
$tapps = Get-Command tapps-mcp -ErrorAction SilentlyContinue
if (-not $tapps) {
    exit 0
}
try {
    $out = & tapps-mcp memory recall --query "$query" --project-root $projDir `
        --max-results 5 --min-score 0.3 --recall-key tapps-mcp-nlt-bundle-preference --recall-key tapps-mcp-nlt-memory-httpcore-fix 2>$null
    if ($out) { Write-Output $out }
} catch {}
exit 0
