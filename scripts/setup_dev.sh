#!/bin/bash
set -e

echo "=== Установка окружения разработки ==="

# Проверка наличия venv
if [ -d "venv_project_med" ]; then
    echo "Виртуальное окружение venv_project_med уже существует."
    read -p "Пересоздать его? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv_project_med
        python3 -m venv venv_project_med
        echo "Окружение пересоздано."
    else
        echo "Используем существующее окружение."
    fi
else
    echo "Создание виртуального окружения venv_project_med..."
    python3 -m venv venv_project_med
fi

source venv_project_med/bin/activate
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    echo "Установка production-зависимостей..."
    pip install -r requirements.txt
fi

if [ -f "requirements-dev.txt" ]; then
    echo "Установка dev-зависимостей..."
    pip install -r requirements-dev.txt
fi

echo "Готово. Активируйте окружение: source venv_project_med/bin/activate"