@echo off
where tapps-mcp >nul 2>nul
if %ERRORLEVEL%==0 (
  tapps-mcp validate-changed --quick %*
) else (
  uvx tapps-mcp validate-changed --quick %*
)
