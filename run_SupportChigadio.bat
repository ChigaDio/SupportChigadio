@echo off
setlocal
cd /d "%~dp0"

set "ZIP=SupportChigadio-windows-x64.zip"
set "DIR=SupportChigadio"

set "NEED_EXTRACT=0"
if not exist "%DIR%" set "NEED_EXTRACT=1"
if exist "VERSION" if exist "%DIR%\.version" (
  fc /b VERSION "%DIR%\.version" >nul 2>&1
  if errorlevel 1 set "NEED_EXTRACT=1"
)

if "%NEED_EXTRACT%"=="1" (
  if not exist "%ZIP%" (
    echo Error: %ZIP% が見つかりません
    pause
    exit /b 1
  )
  echo 解凍中... (%ZIP%)
  if exist "%DIR%" rmdir /s /q "%DIR%"
  powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '.' -Force"
  if exist VERSION copy /y VERSION "%DIR%\.version" >nul
)

if exist "%DIR%\SupportChigadio.bat" (
  call "%DIR%\SupportChigadio.bat"
  exit /b %errorlevel%
)
echo Error: %DIR%\SupportChigadio.bat が見つかりません
pause
exit /b 1
