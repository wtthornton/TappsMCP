@echo off
where tapps-mcp >nul 2>nul
if %ERRORLEVEL%==0 (
  tapps-mcp doctor %*
) else (
  uvx tapps-mcp doctor %*
)
