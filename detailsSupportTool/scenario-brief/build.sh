#!/bin/sh
cd "$(dirname "$0")"
python3 -m pip install pyinstaller
pyinstaller --onefile --name ScenarioBrief --add-data "index.html:." server.py
echo
echo "dist/ScenarioBrief ができました"
