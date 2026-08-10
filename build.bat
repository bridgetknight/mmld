@echo off
cd /d "%~dp0"
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --clean --onedir --noupx --exclude-module matplotlib --exclude-module seaborn --exclude-module sklearn --name export_pipeline src\export_pipeline.py