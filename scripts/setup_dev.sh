#!/bin/bash
# Установка окружения разработки: venv_project_med, пакеты requirements.txt и
# requirements-dev.txt.
#
# Использование:
#   ./scripts/setup_dev.sh                               # Python — /usr/local/bin/python3.11 или первый 3.10+
#   ./scripts/setup_dev.sh --python /usr/bin/python3.12  # конкретный интерпретатор
#   PROJECT_MED_PYTHON=/usr/bin/python3.12 ./scripts/setup_dev.sh
set -e

# Корень проекта — папка над scripts: venv и requirements ищутся и создаются там, откуда бы ни
# запустили скрипт (до 2026-11-07, SC5: в текущей папке)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Выбор интерпретатора — scripts/find_python.sh
source "$SCRIPT_DIR/find_python.sh"

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

echo "=== Установка окружения разработки ==="

# Интерпретатор выбирается до удаления старого venv: не нашёлся — старый остаётся
PYTHON_BIN=$(find_python "$REQUESTED_PYTHON")
echo "Python: $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

# Проверка наличия venv
if [ -d "$ROOT_DIR/venv_project_med" ]; then
    echo "Виртуальное окружение venv_project_med уже существует."
    read -p "Пересоздать его? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$ROOT_DIR/venv_project_med"
        "$PYTHON_BIN" -m venv "$ROOT_DIR/venv_project_med"
        echo "Окружение пересоздано."
    else
        echo "Используем существующее окружение."
    fi
else
    echo "Создание виртуального окружения venv_project_med..."
    "$PYTHON_BIN" -m venv "$ROOT_DIR/venv_project_med"
fi
# (до 2026-10-26, ТД-11: в обеих ветках — python3 -m venv venv_project_med, первый python3
#  в PATH без проверки версии; при python3 3.7 установка пакетов падала ошибкой pip)

source "$ROOT_DIR/venv_project_med/bin/activate"
pip install --upgrade pip

if [ -f "$ROOT_DIR/requirements.txt" ]; then
    echo "Установка production-зависимостей..."
    pip install -r "$ROOT_DIR/requirements.txt"
fi

if [ -f "$ROOT_DIR/requirements-dev.txt" ]; then
    echo "Установка dev-зависимостей..."
    pip install -r "$ROOT_DIR/requirements-dev.txt"
fi

echo "Готово. Активируйте окружение: source "$ROOT_DIR/venv_project_med/bin/activate""