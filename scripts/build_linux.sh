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
chmod +x "$BUILD_DIR/install.sh" "$BUILD_DIR/run.sh" "$BUILD_DIR/setup_prod.sh"
# chmod +x "$BUILD_DIR/install.sh" "$BUILD_DIR/run.sh"
# ↑ до 2026-10-26 (W19): setup_prod.sh в архив не попадал — install.sh падал
#   «./setup_prod.sh: No such file or directory»

# Архивация
tar -czf "$OUTPUT_TAR" "$BUILD_DIR"
rm -rf "$BUILD_DIR"
echo "Создан $OUTPUT_TAR"