@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup-windows.bat first.
  pause
  exit /b 1
)
set "OLLAMA_NO_CLOUD=1"
set "OLLAMA_HOST=http://127.0.0.1:11434"
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
