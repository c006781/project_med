#!/bin/bash
# Установка рабочего окружения: venv_project_med и пакеты requirements.txt.
#
# Использование:
#   ./setup_prod.sh                                  # Python — /usr/local/bin/python3.11 или первый 3.10+
#   ./setup_prod.sh --python /usr/bin/python3.12     # конкретный интерпретатор
#   PROJECT_MED_PYTHON=/usr/bin/python3.12 ./setup_prod.sh
set -e

# Корень — папка скрипта, если в ней лежит requirements.txt (архив Linux), иначе папка над ней
# (репозиторий: scripts/); venv и requirements — там, откуда бы ни запустили скрипт
# (до 2026-11-07, SC5: в текущей папке)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    ROOT_DIR="$SCRIPT_DIR"
else
    ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Выбор интерпретатора — scripts/find_python.sh (в архиве — рядом)
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

echo "=== Установка production-окружения ==="

if [ ! -d "$ROOT_DIR/venv_project_med" ]; then
    PYTHON_BIN=$(find_python "$REQUESTED_PYTHON")
    echo "Создание виртуального окружения venv_project_med ($PYTHON_BIN, $("$PYTHON_BIN" --version 2>&1))..."
    "$PYTHON_BIN" -m venv "$ROOT_DIR/venv_project_med"
fi
# if [ ! -d "venv_project_med" ]; then
#     echo "Создание виртуального окружения venv_project_med..."
#     python3 -m venv venv_project_med
# fi
# ↑ до 2026-10-26 (ТД-11): venv создавался из первого python3 в PATH без проверки версии —
#   при python3 3.7 (/usr/bin/python3) установка пакетов падала ошибкой pip

# Интерпретатор окружения — напрямую: activate разворачивает путь папки как строку оболочки, и в папке
# с $ в имени pip из PATH не находился (до 2026-11-07, SC7: source activate + pip)
VENV_PYTHON="$ROOT_DIR/venv_project_med/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip

if [ -f "$ROOT_DIR/requirements.txt" ]; then
    "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"
fi

echo "Готово. Запуск: ./run.sh"