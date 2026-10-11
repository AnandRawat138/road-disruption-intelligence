@echo off
rem ===========================================================================
rem  Road Disruption Intelligence - first-time setup and start.
rem  Safe to re-run: it never deletes data, never overwrites .env, installs
rem  packages only when missing or changed, and needs no administrator rights.
rem ===========================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "PY=%VENV%\Scripts\python.exe"
set "LOGDIR=%ROOT%runtime\logs"
set "SETUPLOG=%LOGDIR%\setup.log"
title Road Disruption Intelligence - Setup
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo ==================================================================
echo   Road Disruption Intelligence - setup
echo   Folder: %ROOT%
echo   Setup log: runtime\logs\setup.log
echo ==================================================================
echo [%date% %time%] setup started >> "%SETUPLOG%"

rem ---------------------------------------------------------------- 1. Python
echo.
echo [1/7] Checking Python (3.11 or newer)...
set "BASEPY="
if exist "%PY%" (
  echo       Existing virtual environment found.
  goto :venv_ok
)
for %%V in (3.12 3.11 3.13 3.14) do (
  if not defined BASEPY (
    py -%%V -c "import sys" >nul 2>&1 && set "BASEPY=py -%%V"
  )
)
if not defined BASEPY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "BASEPY=python"
)
if not defined BASEPY (
  echo [ERROR] Python 3.11 or newer was not found.
  echo         Install it from the official site https://www.python.org/downloads/windows/
  echo         ^(tick "Add python.exe to PATH" during installation^), then run this script again.
  set "RC=11" & goto :fail
)
for /f "delims=" %%V in ('%BASEPY% --version 2^>^&1') do echo       Using %%V

rem ---------------------------------------------------------------- 2. venv
echo.
echo [2/7] Creating the Python virtual environment (.venv)...
%BASEPY% -m venv "%VENV%" >> "%SETUPLOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Could not create the virtual environment. See runtime\logs\setup.log
  set "RC=12" & goto :fail
)
:venv_ok

rem ---------------------------------------------------------------- 3. backend packages
echo.
echo [3/7] Backend packages...
set "REQ=%ROOT%backend\requirements.txt"
set "NEWHASH="
for /f "delims=" %%H in ('certutil -hashfile "%REQ%" SHA256 ^| findstr /v ":"') do if not defined NEWHASH set "NEWHASH=%%H"
set "OLDHASH="
if exist "%VENV%\.requirements.sha256" set /p OLDHASH=<"%VENV%\.requirements.sha256"
"%PY%" -c "import fastapi, sqlalchemy, httpx, feedparser, uvicorn, dotenv, multipart" >nul 2>&1
if errorlevel 1 set "OLDHASH="
if "!NEWHASH!"=="!OLDHASH!" (
  echo       Already installed and up to date.
) else (
  echo       Installing from PyPI ^(internet connection required^)...
  "%PY%" -m pip install --disable-pip-version-check -r "%REQ%" >> "%SETUPLOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] Package installation failed. Check your internet connection or proxy.
    echo         Details: runtime\logs\setup.log
    set "RC=13" & goto :fail
  )
  > "%VENV%\.requirements.sha256" echo !NEWHASH!
  echo       Installed.
)

rem ---------------------------------------------------------------- 4. web interface
echo.
echo [4/7] Web interface...
if exist "%ROOT%frontend\dist\index.html" if /i not "%~1"=="--rebuild-ui" (
  echo       Pre-built interface found ^(frontend\dist^). Node.js is not required.
  goto :ui_ok
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] The web interface must be built but Node.js/npm was not found.
  echo         Install the LTS version from https://nodejs.org/ and run this script again.
  set "RC=14" & goto :fail
)
pushd "%ROOT%frontend"
if not exist node_modules (
  echo       Installing interface packages ^(internet required^)...
  call npm ci --no-audit --no-fund >> "%SETUPLOG%" 2>&1 || call npm install --no-audit --no-fund >> "%SETUPLOG%" 2>&1
)
echo       Building...
call npm run build >> "%SETUPLOG%" 2>&1
set "BUILD_RC=!ERRORLEVEL!"
popd
if not "!BUILD_RC!"=="0" (
  echo [ERROR] Building the interface failed. See runtime\logs\setup.log
  set "RC=15" & goto :fail
)
:ui_ok

rem ---------------------------------------------------------------- 5. configuration + database
echo.
echo [5/7] Configuration and database...
if not exist "%ROOT%.env" (
  copy /-y "%ROOT%.env.example" "%ROOT%.env" >nul
  echo       Created .env from .env.example ^(local-only defaults; no keys^).
) else (
  echo       Existing .env kept unchanged.
)
pushd "%ROOT%backend"
"%PY%" -m rdi.cli init-db
if errorlevel 1 (
  popd
  echo [ERROR] Database initialisation failed. See runtime\logs\backend.jsonl
  set "RC=16" & goto :fail
)

rem ---------------------------------------------------------------- 6. historical data
echo.
echo [6/7] Historical data...
"%PY%" -m rdi.cli data-report
set "IMPORTS=0"
for /f "delims=" %%S in ('call "%PY%" -m rdi.cli imports-done 2^>nul') do set "IMPORTS=%%S"
if "!IMPORTS!"=="0" (
  echo.
  if defined RDI_AUTO_IMPORT (
    set "ANS=2"
    if /i "%RDI_AUTO_IMPORT%"=="Y" set "ANS=1"
  ) else (
    choice /c YN /m "      No import has been run yet. Import the historical data now (takes a few minutes)"
    set "ANS=!ERRORLEVEL!"
  )
  if "!ANS!"=="1" (
    "%PY%" -m rdi.cli import-history --include-legacy
    if errorlevel 1 echo [WARN] The import reported a problem - check the Data import page after start.
  ) else (
    echo       Skipped. You can import later from the Data import page.
  )
) else (
  echo       Historical data has already been imported ^(!IMPORTS! completed batches^). Re-import is available in the UI.
)
popd

rem ---------------------------------------------------------------- 7. local LLM (optional)
echo.
echo [7/7] Local LLM (optional)...
curl.exe -s -m 3 http://127.0.0.1:11434/api/version >nul 2>&1
if errorlevel 1 (
  echo       Ollama is not running/installed. The app works without it ^(classification needs a
  echo       local model or your own API key^). Run setup_llm.bat any time to set it up.
) else (
  echo       Ollama is running. Use setup_llm.bat or the LLM configuration page to choose a model.
)

echo [%date% %time%] setup finished >> "%SETUPLOG%"
echo.
echo Setup complete. Starting the application...
call "%ROOT%start.bat"
endlocal & exit /b %ERRORLEVEL%

:fail
echo [%date% %time%] setup failed with code %RC% >> "%SETUPLOG%"
echo.
echo Setup stopped with error code %RC%. See TROUBLESHOOTING.md and runtime\logs\setup.log
if not "%RDI_NO_PAUSE%"=="1" pause
endlocal & exit /b %RC%
