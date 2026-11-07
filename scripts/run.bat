@echo off
rem Запуск окна из исходников для разработки; в сборке exe не участвует
rem Запуск из любой текущей папки: venv и main_gui_window.py ищутся от корня проекта
cd /d "%~dp0.."
call venv_project_med\Scripts\activate.bat
python main_gui_window.py
rem до 2026-11-07 (В-23): python interfaces\gui\gui_window\main.py - старая точка входа, без настройки журналов при старте
pause
