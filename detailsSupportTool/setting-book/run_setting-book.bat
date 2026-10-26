@echo off
rem Auto-generated launcher for setting-book (Windows)
setlocal
cd /d "%~dp0"

rem Install requirements.txt if it exists next to this script.
if exist "%~dp0requirements.txt" (
  where python >nul 2>nul
  if not errorlevel 1 (
    echo Installing requirements...
    python -m pip install -q -r "%~dp0requirements.txt"
    if errorlevel 1 echo Warning: failed to install requirements
  ) else (
    echo Warning: Python not found; skipping requirements install
  )
)

rem Run in this console so logs stay visible; closing it stops the server.
"%~dp0setting-book.exe"
echo.
echo Exited with code %errorlevel%.
pause
endlocal
