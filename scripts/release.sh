#!/bin/bash
set -e

# Работа в корне проекта (скрипт можно запускать из любой папки)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # папка scripts (абсолютный путь: дальше cd)
cd "$SCRIPT_DIR/.."

GREEN='\033[0;32m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo "Использование: $0 [patch|minor|major]"
    exit 1
fi
# Часть версии проверяется до первого коммита: раньше неверное слово ловил только version.py,
# уже после коммита «Обновление зависимостей»
case "$1" in
    patch|minor|major) ;;
    *)
        echo "Использование: $0 [patch|minor|major]" >&2
        exit 1
        ;;
esac

# Интерпретатор: в активированном venv — его python; иначе — выбор по scripts/find_python.sh
# (на Linux команда python может отсутствовать или быть Python 2, python3 в PATH — не запускаться)
if [ -n "${VIRTUAL_ENV:-}" ]; then
    PYTHON_BIN=python
else
    source "$SCRIPT_DIR/find_python.sh"
    PYTHON_BIN=$(find_python)
fi

# 1. Обновляем requirements.txt через pip freeze (исключая тестовые)
echo "Обновление requirements.txt..."
bash scripts/pip_freeze.sh
# ↑ до 2026-11-07 (SC4): ./scripts/pip_freeze.sh — у файла не было бита запуска (Permission denied);
#   через bash работает и без бита (на Windows при checkout он может теряться)
# ./scripts/pip_freeze.sh

# 2. Коммитим обновлённые зависимости, если они изменились
# Оба файла вместе (до 2026-11-07, SC8: коммитился только requirements.txt, requirements-dev.txt
# оставался изменённым)
if ! git diff --quiet requirements.txt requirements-dev.txt; then
    git add requirements.txt requirements-dev.txt
    git commit -m "Обновление зависимостей"
fi

# 3. Увеличиваем версию
echo "Увеличиваем версию ($1)..."
"$PYTHON_BIN" scripts/version.py "$1"
# ↑ до 2026-11-07 (SC4): python scripts/version.py $1 — на Linux python может быть Python 2 или отсутствовать
# python scripts/version.py $1

# 4. Читаем новую версию
NEW_VERSION=$(cat VERSION)
TAG="v$NEW_VERSION"

# 5. Коммитим изменение VERSION
git add VERSION
git commit -m "Bump version to $NEW_VERSION"

# 6. Создаём аннотированный тег
git tag -a "$TAG" -m "Release $TAG"

echo -e "${GREEN}Тег $TAG создан. Чтобы запушить:${NC}"
echo "git push origin $TAG"
echo "git push origin main  # если нужно запушить и коммит"