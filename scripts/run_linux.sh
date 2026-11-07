#!/bin/bash
# Запуск из любой текущей папки: venv и main_gui_window.py ищутся рядом со скриптом
cd "$(dirname "$0")"
source venv_project_med/bin/activate
python main_gui_window.py