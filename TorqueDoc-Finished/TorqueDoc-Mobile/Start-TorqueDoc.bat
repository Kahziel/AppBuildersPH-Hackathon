@echo off
setlocal
cd /d "%~dp0"
title TorqueDoc
rem One-click launcher. First run sets everything up (internet needed once); later runs just start the app.

if exist ".venv\Scripts\python.exe" goto check

echo ============================================================
echo  TorqueDoc first-time setup. Internet is needed this once.
echo  This takes a few minutes. Later starts are instant.
echo ============================================================
echo.

:findpython
set "PYEXE="
for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if not defined PYEXE for /f "delims=" %%i in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined PYEXE goto makevenv

if defined TRIED_WINGET goto nopython
where winget >nul 2>nul
if errorlevel 1 goto nopython
echo Python 3.12 is not installed. Installing it for your Windows user now...
echo (Windows may ask for permission. No administrator rights are needed.)
winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
set "TRIED_WINGET=1"
goto findpython

:makevenv
echo Using Python: %PYEXE%
"%PYEXE%" -m venv .venv
if errorlevel 1 goto failed

:install
echo Installing TorqueDoc components...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete.
echo.

:check
rem Repairs an interrupted setup automatically.
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, multipart, pymupdf" >nul 2>nul
if not errorlevel 1 goto start
if defined REPAIRED goto failed
set "REPAIRED=1"
goto install

:start
rem App window component (added in this version). If it cannot install, TorqueDoc opens in the browser instead.
".venv\Scripts\python.exe" -c "import webview" >nul 2>nul
if errorlevel 1 (
  echo Installing the TorqueDoc app window component...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)

rem Desktop and Start menu shortcuts that open TorqueDoc as an app, with no console window.
set "TORQUEDOC_APP_DIR=%CD%"
powershell -NoProfile -Command "$root=$env:TORQUEDOC_APP_DIR; $w=New-Object -ComObject WScript.Shell; foreach($d in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){ $s=$w.CreateShortcut((Join-Path $d 'TorqueDoc.lnk')); $s.TargetPath=Join-Path $root '.venv\Scripts\pythonw.exe'; $s.Arguments=[string][char]34+(Join-Path $root 'desktop.py')+[char]34; $s.WorkingDirectory=$root; $s.IconLocation=Join-Path $root 'torquedoc.ico'; $s.Description='TorqueDoc offline manuals'; $s.Save() }" >nul 2>nul

set "OLLAMA_NO_CLOUD=1"
set "OLLAMA_HOST=http://127.0.0.1:11434"
rem Record completion of first-time setup.
echo ready> ".venv\torquedoc-ready-2"
echo Opening the TorqueDoc app. Next time, use Start-TorqueDoc.bat or the TorqueDoc desktop icon.
start "" ".venv\Scripts\pythonw.exe" desktop.py
exit /b 0

:nopython
echo.
echo Python could not be installed automatically.
echo Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/
echo then double-click Start-TorqueDoc.bat again.
pause
exit /b 1

:failed
echo.
echo Setup failed. Check your internet connection and try again.
echo If it keeps failing, copy the error text above and ask for help.
pause
exit /b 1
