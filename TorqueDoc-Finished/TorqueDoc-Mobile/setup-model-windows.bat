@echo off
setlocal
echo TorqueDoc - one-time local model download. Internet and several GB of free space required.
where ollama >nul 2>nul
if errorlevel 1 (
  echo Install Ollama from ollama.com/download/windows and open a new terminal, then retry.
  pause
  exit /b 1
)
echo Disabling Ollama cloud features for your Windows user account.
setx OLLAMA_NO_CLOUD 1 >nul
if errorlevel 1 (
  echo Could not save the setting. Follow the manual instructions in README.md.
  pause
  exit /b 1
)
set "OLLAMA_NO_CLOUD=1"
set "OLLAMA_HOST=http://127.0.0.1:11434"
echo Quit Ollama from the system tray and relaunch it so the setting takes effect.
echo Then return here to download qwen3:4b.
pause
ollama pull qwen3:4b
if errorlevel 1 (
  echo Download failed. Check that Ollama is running and internet access is available.
  pause
  exit /b 1
)
echo Local model installed. You can disconnect the internet and start TorqueDoc.
pause
