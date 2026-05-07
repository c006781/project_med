@echo off
echo === Установка production-окружения ===
if not exist "venv_project_med" (
    python -m venv venv_project_med
)
call venv_project_med\Scripts\activate.bat
pip install --upgrade pip
if exist requirements.txt pip install -r requirements.txt
echo Готово.
pause