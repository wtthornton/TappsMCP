# TappsMCP PostToolUse hook (tapps_validate_changed)
# Reads the sidecar progress file and echoes a summary to the transcript.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $sec = [math]::Round($d.elapsed_ms / 1000.0, 1)
            $gp = if ($d.all_gates_passed) { "ALL PASSED" } else { "$failed FAILED" }
            Write-Output "[TappsMCP] Validation: $total files, $gp ($($sec)s)"
        } elseif ($d.status -eq "error") {
            Write-Output "[TappsMCP] Validation error: $($d.error)"
        } elseif ($d.status -eq "running") {
            Write-Output "[TappsMCP] Validation in progress: $($d.completed)/$($d.total) files"
        }
    } catch {}
}
exit 0
