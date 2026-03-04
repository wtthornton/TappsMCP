# Local build only: docsmcp.exe + deploy to ~/.local/bin (no CI/PyPI).
# Requires: Python 3.12+, uv. Reuses .venv-pyinstaller if it exists.
# Output: dist\docsmcp.exe → $DeployBin (default %USERPROFILE%\.local\bin\docsmcp.exe)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Deploy target (override with env DEPLOY_BIN)
$DeployBin = if ($env:DEPLOY_BIN_DOCS) { $env:DEPLOY_BIN_DOCS } else { Join-Path $env:USERPROFILE ".local\bin\docsmcp.exe" }

$VenvPyinstaller = ".venv-pyinstaller"
$VenvPython = Join-Path $VenvPyinstaller "Scripts\python.exe"

# 1) Build wheels (tapps-core from root, docs-mcp from package dir so readme resolves)
Write-Host "Building wheels..."
uv build --package tapps-core
Push-Location packages\docs-mcp
uv build
Pop-Location
$Wheels = Get-ChildItem -Path "dist" -Filter "docs_mcp*.whl" -ErrorAction SilentlyContinue
if (-not $Wheels) {
    Write-Error "No docs_mcp wheel in dist/. Build failed."
}

# 2) Install PyInstaller + wheels into venv
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating $VenvPyinstaller..."
    python -m venv $VenvPyinstaller
}
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install pyinstaller --quiet
# Install wheels we built (use newest if multiple versions in dist)
& $VenvPython -m pip install (Get-ChildItem dist -Filter "tapps_core*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName --quiet
& $VenvPython -m pip install (Get-ChildItem dist -Filter "docs_mcp*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName --quiet

# 3) Build exe using spec (bundles templates + data files)
Write-Host "Running PyInstaller..."
& $VenvPython -m PyInstaller docsmcp.spec --clean

$Exe = "dist\docsmcp.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "Build failed: $Exe not found"
}

Write-Host "Built: $Exe"
& $Exe --version

# 4) Deploy to ~/.local/bin (skip if target is in use)
$DeployDir = Split-Path -Parent $DeployBin
if (-not (Test-Path $DeployDir)) {
    New-Item -ItemType Directory -Path $DeployDir -Force | Out-Null
    Write-Host "Created $DeployDir"
}
try {
    Copy-Item -Path $Exe -Destination $DeployBin -Force
    Write-Host "Deployed: $DeployBin"
    & $DeployBin --version
} catch {
    Write-Warning "Deploy failed (close $DeployBin if open): $_"
    Write-Host "Exe is at: $((Resolve-Path $Exe).Path)"
}
