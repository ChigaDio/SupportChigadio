@echo off
setlocal
set "SUPPORT_ROOT=%~dp0"
set "PYTHONUNBUFFERED=1"
cd /d "%SUPPORT_ROOT%"
if not exist "%SUPPORT_ROOT%MainSupport.exe" (
  echo MainSupport.exe was not found.
  pause
  exit /b 1
)
"%SUPPORT_ROOT%MainSupport.exe"
pause
