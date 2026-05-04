#!/usr/bin/env python3
"""
Сборка единого .exe файла для Windows с помощью PyInstaller.
Запуск: python build_exe.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    # Проверка наличия PyInstaller
    pyinstaller_path = shutil.which('pyinstaller')
    if not pyinstaller_path:
        print("Ошибка: PyInstaller не найден. Установите: pip install pyinstaller")
        sys.exit(1)

    # Определяем разделитель для --add-data в зависимости от ОС
    separator = ';' if sys.platform == 'win32' else ':'

    # Базовые параметры
    cmd = [
        pyinstaller_path,
        "--onefile",               # Один исполняемый файл
        "--windowed",              # Без консольного окна (GUI)
        "--name", "MedicalApp",    # Имя выходного файла
        "--add-data", f"app{separator}app",
        "--add-data", f"interfaces{separator}interfaces",
    ]

    # Добавляем скрытые импорты для корректной упаковки зависимостей
    hidden_imports = [
        'sqlalchemy.sql.default',
        'sqlalchemy.dialects.sqlite',
        'yadisk',
        'cryptography',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.primitives',
        'pydantic',
        'pydantic_core',
        'msgpack',
        'dotenv',
        'requests',
        'PySide6',
        'shiboken6',
    ]
    for mod in hidden_imports:
        cmd.extend(['--hidden-import', mod])

    # Собираем все пакеты PySide6 (плагины, переводы)
    cmd.extend(['--collect-all', 'PySide6'])

    # Если есть файл конфигурации, добавляем его
    if Path('config.msgpack').exists():
        cmd.extend(['--add-data', f"config.msgpack{separator}."])

    # Добавляем иконку (опционально, если есть файл icon.ico)
    # if Path('icon.ico').exists():
    #     cmd.extend(['--icon', 'icon.ico'])

    # Точка входа
    cmd.append('main_gui_window.py')

    print("Запуск PyInstaller с параметрами:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

    # Результат в папке dist/
    print("\nСборка завершена. Исполняемый файл: dist/MedicalApp.exe")

if __name__ == "__main__":
    main()