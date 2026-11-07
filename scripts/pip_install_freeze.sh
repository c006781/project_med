#!/bin/bash
# Установка пакетов из requirements.txt в активированное окружение (из любой папки).
set -e

cd "$(dirname "$0")/.."
pip install -r ./requirements.txt
# ↑ до 2026-11-07 (SC5): одна строка pip install -r ./requirements.txt — работала только из корня проекта
