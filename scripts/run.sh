#!/bin/bash
# Запуск окна из исходников для разработки; в сборке exe и в архиве Linux не участвует
# Запуск из любой текущей папки: venv и main_gui_window.py ищутся от корня проекта
cd "$(dirname "$0")/.."
source venv_project_med/bin/activate
python main_gui_window.py
# ↑ до 2026-11-07 (В-23): python interfaces/gui/gui_window/main.py — старая точка входа, без настройки журналов при старте
