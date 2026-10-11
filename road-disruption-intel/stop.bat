@echo off
rem ===========================================================================
rem  Road Disruption Intelligence - stop the application.
rem  Only stops the backend started from THIS folder (verified by command line
rem  and by this project's .venv python). Never touches other Python/Node apps.
rem ===========================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "RUNTIME=%ROOT%\runtime"
set "PIDFILE=%RUNTIME%\backend.pid"
set "STOPFILE=%RUNTIME%\stop.request"
set "PT=powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\process_tools.ps1""
set "RC=0"
set "PID="

if exist "%PIDFILE%" set /p PID=<"%PIDFILE%"
if defined PID (
  %PT% -Action verify -ProcId !PID! -Root "%ROOT%" >nul 2>&1
  if errorlevel 1 (
    echo Recorded process !PID! is not this application ^(stale PID file^). Cleaning up.
    del "%PIDFILE%" >nul 2>&1
    set "PID="
  )
)
if not defined PID (
  for /f %%P in ('%PT% -Action find -Root "%ROOT%" 2^>nul') do set "PID=%%P"
)
if not defined PID (
  echo The application is not running.
  goto :end
)

echo Requesting a graceful shutdown of the backend ^(process %PID%^)...
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
type nul > "%STOPFILE%"
set /a T=0
:waitstop
%PT% -Action alive -ProcId %PID% -Root "%ROOT%" >nul 2>&1
if errorlevel 1 goto :stopped
set /a T+=1
if !T! GEQ 20 goto :force
ping -n 2 127.0.0.1 >nul
goto :waitstop

:force
echo The backend did not exit within 20 seconds; terminating process %PID% and its children only.
taskkill /PID %PID% /T /F >nul 2>&1
if errorlevel 1 set "RC=1"

:stopped
del "%STOPFILE%" >nul 2>&1
del "%PIDFILE%" >nul 2>&1
echo Stopped.

:end
if not "%RDI_NO_PAUSE%"=="1" ping -n 4 127.0.0.1 >nul
endlocal & exit /b %RC%
