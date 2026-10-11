@echo off
rem ===========================================================================
rem  Road Disruption Intelligence - start the application (after setup).
rem  Does not reinstall anything. Safe to run twice: an already running
rem  instance is detected and simply opened in the browser.
rem ===========================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "RUNTIME=%ROOT%runtime"
set "LOGDIR=%RUNTIME%\logs"
set "PIDFILE=%RUNTIME%\backend.pid"
set "PORT=8000"
set "HOST=127.0.0.1"
title Road Disruption Intelligence

if exist "%ROOT%.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%.env") do (
    if /i "%%A"=="APP_PORT" if not "%%B"=="" set "PORT=%%B"
    if /i "%%A"=="APP_HOST" if not "%%B"=="" set "HOST=%%B"
  )
)
set "BROWSE_HOST=%HOST%"
if "%HOST%"=="0.0.0.0" set "BROWSE_HOST=127.0.0.1"
set "URL=http://%BROWSE_HOST%:%PORT%/"

if not exist "%PY%" (
  echo [ERROR] The application is not set up yet. Run setup_and_start.bat first.
  set "RC=10" & goto :end
)
if not exist "%ROOT%frontend\dist\index.html" (
  echo [WARN] The web interface has not been built. Run setup_and_start.bat to build it.
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem --- Already running? (only if the healthy server is THIS folder's process) -----
call :health
if "!HEALTHY!"=="1" (
  set "OURS=0"
  if exist "%PIDFILE%" (
    set /p RUNPID=<"%PIDFILE%"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\process_tools.ps1" -Action verify -ProcId !RUNPID! -Root "%ROOT%." >nul 2>&1
    if not errorlevel 1 set "OURS=1"
  )
  if "!OURS!"=="1" (
    echo The application is already running at %URL%
    start "" "%URL%"
    set "RC=0" & goto :end
  )
  echo [ERROR] Port %PORT% is already used by another program or another copy of this application.
  echo         Stop it, or set APP_PORT=8010 ^(for example^) in this folder's .env file and run start.bat again.
  set "RC=20" & goto :end
)

rem --- Stale PID file from a crash: verify before trusting it -----------------
if exist "%PIDFILE%" (
  set /p OLDPID=<"%PIDFILE%"
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\process_tools.ps1" -Action verify -ProcId !OLDPID! -Root "%ROOT%." >nul 2>&1
  if errorlevel 1 (
    del "%PIDFILE%" >nul 2>&1
  ) else (
    echo [INFO] The backend ^(process !OLDPID!^) is already starting. Waiting for it...
  )
)

rem --- Port conflict check -----------------------------------------------------
if not exist "%PIDFILE%" (
  netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
  if not errorlevel 1 (
    echo [ERROR] Port %PORT% is already used by another program.
    echo         Close that program, or set APP_PORT=8010 ^(for example^) in the .env file and run start.bat again.
    for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do echo         Process using the port: PID %%P
    set "RC=20" & goto :end
  )
  echo Starting the backend ^(logs: runtime\logs\server.log^)...
  start "RDI Backend - close this window to stop" /D "%ROOT%backend" /MIN cmd /c ""%PY%" -m rdi.server >> "%LOGDIR%\server.log" 2>&1"
)

rem --- Wait for readiness (up to 90 s) ---------------------------------------
set /a TRIES=0
:wait
call :health
if "!HEALTHY!"=="1" goto :ready
set /a TRIES+=1
if !TRIES! GEQ 45 goto :notready
ping -n 3 127.0.0.1 >nul
goto :wait

:ready
echo.
echo  Road Disruption Intelligence is running:  %URL%
echo  Stop it with stop.bat. Logs are in runtime\logs.
echo.
start "" "%URL%"
set "RC=0" & goto :end

:notready
echo [ERROR] The backend did not become ready within 90 seconds.
echo         Last lines of runtime\logs\server.log:
powershell -NoProfile -Command "if(Test-Path '%LOGDIR%\server.log'){Get-Content '%LOGDIR%\server.log' -Tail 25}"
echo         See TROUBLESHOOTING.md for help.
set "RC=30" & goto :end

:health
set "HEALTHY=0"
for /f %%C in ('curl.exe -s -o nul -m 3 -w "%%{http_code}" "http://%BROWSE_HOST%:%PORT%/api/health" 2^>nul') do if "%%C"=="200" set "HEALTHY=1"
exit /b 0

:end
if not "%RDI_NO_PAUSE%"=="1" if not "%RC%"=="0" pause
endlocal & exit /b %RC%
