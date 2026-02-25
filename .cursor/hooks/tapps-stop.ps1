# TappsMCP stop hook (Cursor)
# If validation passed recently (marker < 60 min), output no followup (avoids loop).
# Otherwise prompt to run tapps_validate_changed.
$null = $input | Out-Null
$marker = ".tapps-mcp/sessions/last_validate_ok"
if (Test-Path $marker) {
    $age = (Get-Date) - (Get-Item $marker -ErrorAction SilentlyContinue).LastWriteTime
    if ($age -and $age.TotalMinutes -le 60) {
        Write-Output "{}"
        exit 0
    }
}
$msg = "Before ending: please run tapps_validate_changed"
$msg += " to confirm all changed files pass quality gates."
Write-Output "{`"followup_message`": `"$msg`"}"
exit 0
