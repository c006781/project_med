@echo off
cd /d %~dp0\..
call venv_project_med\Scripts\activate.bat
python scripts\build_win.py
pause