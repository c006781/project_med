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
cp main_gui_window.py main_cli.py "$BUILD_DIR/"
cp requirements.txt "$BUILD_DIR/"
cp VERSION "$BUILD_DIR/"

# Копируем скрипты для дистрибутива
cp scripts/install_linux.sh "$BUILD_DIR/install.sh"
cp scripts/run_linux.sh "$BUILD_DIR/run.sh"
chmod +x "$BUILD_DIR/install.sh" "$BUILD_DIR/run.sh"

# Архивация
tar -czf "$OUTPUT_TAR" "$BUILD_DIR"
rm -rf "$BUILD_DIR"
echo "Создан $OUTPUT_TAR"