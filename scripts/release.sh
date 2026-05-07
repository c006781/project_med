#!/bin/bash
set -e

GREEN='\033[0;32m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo "Использование: $0 [patch|minor|major]"
    exit 1
fi

# 1. Обновляем requirements.txt через pip freeze (исключая тестовые)
echo "Обновление requirements.txt..."
./scripts/pip_freeze.sh

# 2. Коммитим обновлённые зависимости, если они изменились
if ! git diff --quiet requirements.txt; then
    git add requirements.txt
    git commit -m "Обновление зависимостей"
fi

# 3. Увеличиваем версию
echo "Увеличиваем версию ($1)..."
python scripts/version.py $1

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