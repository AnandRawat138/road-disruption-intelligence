@echo off
rem Road Disruption Intelligence - setup diagnostics (read-only checks).
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
echo ===== Road Disruption Intelligence diagnostics =====
where python >nul 2>&1 && (for /f "delims=" %%V in ('python --version 2^>^&1') do echo System Python: %%V) || echo System Python: not on PATH
where py >nul 2>&1 && echo Python launcher: available || echo Python launcher: not found
where node >nul 2>&1 && (for /f "delims=" %%V in ('node --version') do echo Node.js: %%V ^(only needed to rebuild the UI^)) || echo Node.js: not found ^(only needed to rebuild the UI^)
if exist "%PY%" (
  pushd "%~dp0backend"
  "%PY%" -m rdi.cli diagnose
  popd
) else (
  echo Application environment: NOT SET UP ^(run setup_and_start.bat^)
)
if not "%RDI_NO_PAUSE%"=="1" pause
endlocal
