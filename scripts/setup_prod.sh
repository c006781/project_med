#!/bin/bash
set -e

echo "=== Установка production-окружения ==="

if [ ! -d "venv_project_med" ]; then
    echo "Создание виртуального окружения venv_project_med..."
    python3 -m venv venv_project_med
fi

source venv_project_med/bin/activate
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

echo "Готово. Запуск: ./run.sh"