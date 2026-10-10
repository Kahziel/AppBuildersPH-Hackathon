@echo off
setlocal
cd /d "%~dp0"
title Build the TorqueDoc website
if not exist ".venv\Scripts\python.exe" (
  echo Run TorqueDoc.exe or Start-TorqueDoc.bat once first, so Python is set up.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" website\build.py
if errorlevel 1 (
  echo The website could not be built. Copy the messages above and ask for help.
  pause
  exit /b 1
)
echo.
echo The website is in website\dist. Upload that whole folder to your web host.
echo To try it on this computer first, double-click preview-website.bat.
pause
