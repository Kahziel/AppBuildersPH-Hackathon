@echo off
setlocal
cd /d "%~dp0"
title Build the standalone TorqueDoc app
rem Makes dist\TorqueDoc\TorqueDoc.exe and dist\TorqueDoc-portable.zip: a TorqueDoc that runs on any
rem Windows 10/11 PC without installing Python. Only needed to share TorqueDoc with others.

if not exist ".venv\Scripts\python.exe" (
  echo Run Start-TorqueDoc.bat once first, so the build tools can be set up.
  pause
  exit /b 1
)
echo Building the standalone TorqueDoc app. Internet is needed once; this takes a few minutes.
echo.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller==6.22.3
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import webview" >nul 2>nul
if errorlevel 1 echo WARNING: the app window component is missing; the built app will open in the browser instead.

if exist "build\desktop" rmdir /s /q "build\desktop"
if exist "dist\TorqueDoc" rmdir /s /q "dist\TorqueDoc"
if exist "dist\TorqueDoc-portable.zip" del /q "dist\TorqueDoc-portable.zip"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --workpath build\desktop torquedoc.spec
if errorlevel 1 goto failed

echo Adding the built-in library...
xcopy "library" "dist\TorqueDoc\library\" /e /i /q /y >nul
if errorlevel 1 goto failed
copy /y "START-HERE-PORTABLE.txt" "dist\TorqueDoc\READ-ME-FIRST.txt" >nul
echo Making the zip file to share...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\TorqueDoc' -DestinationPath 'dist\TorqueDoc-portable.zip' -Force"
if errorlevel 1 goto failed

echo.
echo Done.
echo   App:          dist\TorqueDoc\TorqueDoc.exe
echo   To share:     dist\TorqueDoc-portable.zip
start "" explorer "%CD%\dist"
pause
exit /b 0

:failed
echo.
echo The build failed. Copy the messages above and ask for help.
pause
exit /b 1
