#!/bin/bash
set -e
cd "$(dirname "$0")/.."

VERSION=$(cat VERSION 2>/dev/null || echo "0.0.0")
BUILD_DIR="MedicalApp-linux"
OUTPUT_TAR="MedicalApp-linux.tar.gz"

rm -rf "$BUILD_DIR" "$OUTPUT_TAR"
mkdir -p "$BUILD_DIR"

# Копируем исходники
cp -r app interfaces "$BUILD_DIR/"
# Импорт из Word (окно импортирует parsers.word_importer): только модули, без журналов,
# фото и кэша, которые остаются в parsers/ после запусков
mkdir -p "$BUILD_DIR/parsers"
cp parsers/*.py "$BUILD_DIR/parsers/"
# ↑ до 2026-10-26 (W19): parsers/ в архив не попадал — импорт из Word в Linux-версии падал
#   ModuleNotFoundError
cp main_gui_window.py main_cli.py "$BUILD_DIR/"
cp requirements.txt "$BUILD_DIR/"
cp VERSION "$BUILD_DIR/"

# Копируем скрипты для дистрибутива
cp scripts/install_linux.sh "$BUILD_DIR/install.sh"
cp scripts/run_linux.sh "$BUILD_DIR/run.sh"
# install.sh вызывает ./setup_prod.sh (venv и пакеты из requirements.txt) — он нужен рядом
cp scripts/setup_prod.sh "$BUILD_DIR/setup_prod.sh"
# Выбор интерпретатора Python — его подключает setup_prod.sh (ТД-11)
cp scripts/find_python.sh "$BUILD_DIR/find_python.sh"
chmod +x "$BUILD_DIR/install.sh" "$BUILD_DIR/run.sh" "$BUILD_DIR/setup_prod.sh"
# chmod +x "$BUILD_DIR/install.sh" "$BUILD_DIR/run.sh"
# ↑ до 2026-10-26 (W19): setup_prod.sh в архив не попадал — install.sh падал
#   «./setup_prod.sh: No such file or directory»

# Кэш байт-кода из рабочей папки (после запусков и тестов) в архив не нужен
find "$BUILD_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
# ↑ до 2026-11-07 (SC1): кэш не удалялся — при сборке в папке, где запускали программу, в архив
#   попадали app/**/__pycache__ и interfaces/**/__pycache__ (.pyc под чужую версию Python)

# Данные из рабочей папки (журналы, фото, настройки, базы) в код не попадают: манифест с такими
# путями автообновление отклонит (app/updater.py, validate_manifest_path)
find "$BUILD_DIR" -type d \
    \( -name logs -o -name logs_parser -o -name 'photos*' -o -name MedicalAppUpdates \) \
    -prune -exec rm -rf {} +
find "$BUILD_DIR" -type f \
    \( -name '*.env' -o -name '*.db' -o -name '*.db-*' -o -name '*.sqlite' -o -name '*.sqlite3' \
    -o -name '*.msgpack' -o -name '*.log' -o -name '*.log.*' -o -name '*.part' \) \
    -delete

# Метка и манифест для автообновления (app/UPDATER.md, раздел 1.3). Метка: «это установленный
# дистрибутив». Манифест: все файлы кода поимённо — обновление заменяет только их, поэтому данные
# в папках кода (parsers/logs, parsers/photos) не затрагиваются
MARKER_FILE=".medicalapp_dist"
MANIFEST_FILE=".medicalapp_manifest"
printf 'MedicalApp Linux %s\n' "$VERSION" > "$BUILD_DIR/$MARKER_FILE"
# Только обычные файлы и папки: ссылки автообновление не принимает
if [ -n "$(find "$BUILD_DIR" ! -type f ! -type d)" ]; then
    echo "Ошибка: в дистрибутиве есть ссылки или спецфайлы:" >&2
    find "$BUILD_DIR" ! -type f ! -type d >&2
    exit 1
fi
{
    echo "# medicalapp manifest v1"
    {
        echo "$MANIFEST_FILE"
        (cd "$BUILD_DIR" && find . -type f -printf '%P\n')
    } | LC_ALL=C sort
} > "$BUILD_DIR.manifest.tmp"
mv "$BUILD_DIR.manifest.tmp" "$BUILD_DIR/$MANIFEST_FILE"

# Архивация
tar -czf "$OUTPUT_TAR" "$BUILD_DIR"
rm -rf "$BUILD_DIR"
echo "Создан $OUTPUT_TAR"