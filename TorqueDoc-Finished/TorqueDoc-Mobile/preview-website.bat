@echo off
setlocal
cd /d "%~dp0"
title TorqueDoc website preview
if not exist ".venv\Scripts\python.exe" (
  echo Run Start-TorqueDoc.bat once first, so Python is set up.
  pause
  exit /b 1
)
if not exist "website\dist\index.html" ".venv\Scripts\python.exe" website\build.py
".venv\Scripts\python.exe" website\preview.py
pause
