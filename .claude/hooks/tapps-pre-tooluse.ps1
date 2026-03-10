# TappsMCP PreToolUse hook
# Blocks dangerous Bash commands (rm -rf /, git push --force, git reset --hard, git clean -f).
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $command = $data.tool_input.command
} catch {
    $command = ""
}
if (-not $command) {
    exit 0
}

$dangerousPatterns = @(
    'rm\s+-rf\s+/',
    'git\s+push\s+--force',
    'git\s+push\s+-f\b',
    'git\s+reset\s+--hard',
    'git\s+clean\s+-f'
)

foreach ($pattern in $dangerousPatterns) {
    if ($command -match $pattern) {
        Write-Output "BLOCKED: Dangerous command detected: $command"
        Write-Output "This command matches pattern '$pattern' and could cause irreversible damage."
        Write-Output "Please use a safer alternative."
        exit 2
    }
}
exit 0
