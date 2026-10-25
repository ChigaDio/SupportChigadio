@echo off
cd /d %~dp0
python -m pip install pyinstaller
pyinstaller --onefile --name ScenarioBrief --add-data "index.html;." server.py
echo.
echo dist\ScenarioBrief.exe ができました
pause
