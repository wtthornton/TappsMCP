# tapps-mcp-hook-version: 3.12.43
# tapps-mcp-hook-content-sha: 0eed38f2
# TappsMCP beforeMCPExecution hook
# Logs MCP tool invocations and reminds to call session_start.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $tool = if ($data.tool_name) { $data.tool_name }
             elseif ($data.tool) { $data.tool }
             else { "unknown" }
} catch {
    $tool = "unknown"
}
if ($tool -match '^tapps_') {
    $sentinel = "$env:TEMP\.tapps-session-started-$PID"
    $agentMsg = $null
    if ($tool -eq 'tapps_session_start') {
        $null = New-Item -ItemType File -Path $sentinel -Force
    } elseif (-not (Test-Path $sentinel)) {
        $agentMsg = "REMINDER: Call tapps_session_start() first for best results."
    }
    if ($agentMsg) {
        @{ permission = "allow"; agent_message = $agentMsg } | ConvertTo-Json -Compress
    } else {
        '{"permission":"allow"}'
    }
} else {
    '{"permission":"allow"}'
}
Write-Host "[TappsMCP] MCP tool invoked: $tool" -ForegroundColor Cyan
exit 0
