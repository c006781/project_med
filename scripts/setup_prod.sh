#!/bin/bash
# Установка рабочего окружения: venv_project_med и пакеты requirements.txt.
#
# Использование:
#   ./setup_prod.sh                                  # Python — /usr/local/bin/python3.11 или первый 3.10+
#   ./setup_prod.sh --python /usr/bin/python3.12     # конкретный интерпретатор
#   PROJECT_MED_PYTHON=/usr/bin/python3.12 ./setup_prod.sh
set -e

# Выбор интерпретатора — scripts/find_python.sh (в архиве — рядом)
source "$(dirname "$0")/find_python.sh"

REQUESTED_PYTHON=""   # --python <путь>; пусто — выбор по умолчанию
while [ $# -gt 0 ]; do
    case "$1" in
        --python)
            REQUESTED_PYTHON="$2"
            shift 2
            ;;
        *)
            echo "Неизвестный параметр: $1 (есть только --python <путь>)" >&2
            exit 2
            ;;
    esac
done

echo "=== Установка production-окружения ==="

if [ ! -d "venv_project_med" ]; then
    PYTHON_BIN=$(find_python "$REQUESTED_PYTHON")
    echo "Создание виртуального окружения venv_project_med ($PYTHON_BIN, $("$PYTHON_BIN" --version 2>&1))..."
    "$PYTHON_BIN" -m venv venv_project_med
fi
# if [ ! -d "venv_project_med" ]; then
#     echo "Создание виртуального окружения venv_project_med..."
#     python3 -m venv venv_project_med
# fi
# ↑ до 2026-10-26 (ТД-11): venv создавался из первого python3 в PATH без проверки версии —
#   при python3 3.7 (/usr/bin/python3) установка пакетов падала ошибкой pip

source venv_project_med/bin/activate
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

echo "Готово. Запуск: ./run.sh"