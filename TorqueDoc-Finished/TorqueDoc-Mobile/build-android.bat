@echo off
cd /d "%~dp0"
py -3 build-android.py
if errorlevel 1 (
  echo Build failed. See the message above and ANDROID-README.md.
) else (
  echo APK ready in output\TorqueDoc-Android.apk
)
pause
