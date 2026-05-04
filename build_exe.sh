#!/bin/bash
# build_exe.sh – активирует venv и запускает сборку .exe (требуется Windows-среда)

source venv_project_med/bin/activate
pip install pyinstaller
python build_exe.py
deactivate