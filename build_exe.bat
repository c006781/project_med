@echo off
call venv_project_med\Scripts\activate.bat
pip install pyinstaller
python build_exe.py
pause