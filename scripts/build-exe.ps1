# Build tapps-mcp.exe with PyInstaller (Windows).
# Requires: Python 3.12+, uv or pip. Creates .venv-pyinstaller if missing.
# Output: dist\tapps-mcp.exe

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPyinstaller = ".venv-pyinstaller"
$VenvPython = Join-Path $VenvPyinstaller "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating $VenvPyinstaller and installing PyInstaller + project..."
    python -m venv $VenvPyinstaller
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install pyinstaller
    & $VenvPython -m pip install -e "."
} else {
    Write-Host "Using existing $VenvPyinstaller; ensure project is installed (pip install -e .)."
}

$SpecFile = "tapps_mcp.spec"
if (-not (Test-Path $SpecFile)) {
    Write-Error "Spec file not found: $SpecFile"
}

Write-Host "Running PyInstaller with spec file ($SpecFile)..."
& $VenvPython -m PyInstaller $SpecFile --clean

$Exe = "dist\tapps-mcp.exe"
if (Test-Path $Exe) {
    Write-Host "Built: $Exe"
    & $Exe --version
} else {
    Write-Error "Build failed: $Exe not found"
}
