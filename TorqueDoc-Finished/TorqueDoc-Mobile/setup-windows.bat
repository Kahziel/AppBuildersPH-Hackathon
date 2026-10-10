@echo off
setlocal
cd /d "%~dp0"
echo TorqueDoc - one-time Python setup. Internet is needed for this step.
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.12 or 3.13 from python.org with the launcher enabled.
  pause
  exit /b 1
)
set "PYVER="
py -3.12 -c "import sys" >nul 2>nul && set "PYVER=3.12"
if not defined PYVER py -3.13 -c "import sys" >nul 2>nul && set "PYVER=3.13"
if not defined PYVER (
  echo Install Python 3.12 or 3.13 64-bit before running this script. See README.md.
  pause
  exit /b 1
)
echo Using Python %PYVER%.
if not exist ".venv\Scripts\python.exe" py -%PYVER% -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Python setup is complete. Keyword search is ready.
echo Install Ollama, then run setup-model-windows.bat once to download the local AI model.
echo Run start-windows.bat to open TorqueDoc.
pause
exit /b 0
:failed
echo Setup failed. Keep this error text and check README.md.
pause
exit /b 1
