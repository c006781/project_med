#!/bin/bash
set -e

echo "Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

echo "Установка зависимостей из requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Установка завершена. Для запуска выполните ./run.sh"