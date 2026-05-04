#!/bin/bash
# run.sh – запуск GUI в режиме разработки

source venv_project_med/bin/activate
pip install -r requirements.txt   # опционально, для обновления
python interfaces/gui/gui_window/main.py