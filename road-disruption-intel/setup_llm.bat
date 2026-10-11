@echo off
rem ===========================================================================
rem  Road Disruption Intelligence - optional local LLM (Ollama) setup.
rem  Detects Ollama, checks hardware, lets you choose a model and downloads it
rem  ONLY after you confirm. Never stores API keys.
rem ===========================================================================
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] Run setup_and_start.bat first to install the application.
  set "RC=10" & goto :end
)
pushd "%~dp0backend"
"%PY%" -m rdi.ollama_cli
set "RC=%ERRORLEVEL%"
popd
:end
if not "%RDI_NO_PAUSE%"=="1" pause
endlocal & exit /b %RC%
