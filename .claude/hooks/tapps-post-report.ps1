# TappsMCP PostToolUse hook (tapps_report)
# Reads the report sidecar progress file and echoes a summary.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $results = @($d.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "[TappsMCP] Report: $total files scored, avg $avg/100"
            } else {
                Write-Output "[TappsMCP] Report: $total files scored"
            }
        } elseif ($d.status -eq "error") {
            Write-Output "[TappsMCP] Report error: $($d.error)"
        } elseif ($d.status -eq "running") {
            Write-Output "[TappsMCP] Report in progress: $($d.completed)/$($d.total) files"
        }
    } catch {}
}
exit 0
