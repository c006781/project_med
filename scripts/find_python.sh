#!/bin/bash
# Выбор интерпретатора Python для создания venv (подключается через source из
# setup_prod.sh и setup_dev.sh; в архиве Linux лежит рядом с ними).
#
# Порядок выбора:
#   1. явно указанный — параметр --python <путь> или переменная PROJECT_MED_PYTHON;
#      не подходит — ошибка (другой молча не берётся);
#   2. по умолчанию — /usr/local/bin/python3.11;
#   3. первый подходящий из python3.11, python3.10, python3 в PATH.
# Подходит — запускается и версия не ниже PROJECT_MED_MIN_PYTHON (3.10: проект проверяется
# на 3.10 — Windows, CI — и на 3.11 — Linux; пакеты requirements.txt требуют 3.9+).
#
# Пример:
#   source "$(dirname "$0")/find_python.sh"
#   PYTHON_BIN=$(find_python "$REQUESTED_PYTHON")   # пусто — выбор по умолчанию
#   "$PYTHON_BIN" -m venv venv_project_med

PROJECT_MED_DEFAULT_PYTHON="/usr/local/bin/python3.11"   # интерпретатор по умолчанию
PROJECT_MED_MIN_PYTHON="3.10"                            # минимальная версия

# python_is_suitable <интерпретатор> — 0, если запускается и версия не ниже минимальной
python_is_suitable() {
    local candidate="$1"   # путь или имя команды

    command -v "$candidate" > /dev/null 2>&1 || return 1
    "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= tuple(map(int, '$PROJECT_MED_MIN_PYTHON'.split('.'))) else 1)" \
        > /dev/null 2>&1
}

# find_python [<явно указанный интерпретатор>] — печатает выбранный интерпретатор;
# ничего не подошло — сообщение в stderr и код 1
find_python() {
    local requested="${1:-$PROJECT_MED_PYTHON}"   # параметр или переменная окружения
    local candidate                               # очередной кандидат

    # Явно указанный — только он: ошибка пользователя видна сразу
    if [ -n "$requested" ]; then
        if python_is_suitable "$requested"; then
            echo "$requested"
            return 0
        fi
        echo "Ошибка: интерпретатор '$requested' не найден или версия ниже $PROJECT_MED_MIN_PYTHON." >&2
        return 1
    fi

    for candidate in \
        "$PROJECT_MED_DEFAULT_PYTHON" \
        python3.11 \
        python3.10 \
        python3
    do
        if python_is_suitable "$candidate"; then
            echo "$candidate"
            return 0
        fi
    done

    echo "Ошибка: не найден Python $PROJECT_MED_MIN_PYTHON+ (проверены $PROJECT_MED_DEFAULT_PYTHON, python3.11, python3.10, python3)." >&2
    echo "Укажите интерпретатор: --python <путь> или PROJECT_MED_PYTHON=<путь>." >&2
    return 1
}
