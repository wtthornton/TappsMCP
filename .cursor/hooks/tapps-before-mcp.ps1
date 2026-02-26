# TappsMCP beforeMCPExecution hook
# Logs MCP tool invocations and reminds to call session_start.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $tool = if ($data.tool) { $data.tool } else { "unknown" }
} catch {
    $tool = "unknown"
}
if ($tool -match '^tapps_') {
    $sentinel = "$env:TEMP\.tapps-session-started-$PID"
    if ($tool -eq 'tapps_session_start') {
        $null = New-Item -ItemType File -Path $sentinel -Force
    } elseif (-not (Test-Path $sentinel)) {
        Write-Output "REMINDER: Call tapps_session_start() first for best results."
    }
}
Write-Host "[TappsMCP] MCP tool invoked: $tool" -ForegroundColor Cyan
exit 0
