# scripts/build_win.py
"""
Сборка Windows .exe с помощью PyInstaller.
Запускать из корня проекта или через build_win.bat.
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    # Корень проекта (на два уровня выше этого скрипта)
    root_dir = Path(__file__).parent.parent.resolve()
    os.chdir(root_dir)

    # Проверяем наличие PyInstaller
    if not shutil.which('pyinstaller'):
        print("Error: PyInstaller not installed. Run: pip install pyinstaller")
        sys.exit(1)

    separator = ';' if sys.platform == 'win32' else ':'

    cmd = [
        'pyinstaller',
        '--onefile',
        '--windowed',
        '--name', 'MedicalApp',
        '--add-data', f'app{separator}app',
        '--add-data', f'interfaces{separator}interfaces',
        # '--add-data', f'scripts{separator}scripts',
        '--hidden-import', 'sqlalchemy.sql.default',
        '--hidden-import', 'sqlalchemy.dialects.sqlite',
        '--hidden-import', 'yadisk',
        '--hidden-import', 'cryptography',
        '--hidden-import', 'pydantic',
        '--hidden-import', 'msgpack',
        '--hidden-import', 'dotenv',
        '--collect-all', 'PySide6',
        'main_gui_window.py'
    ]

    version_file = root_dir / 'VERSION'
    if version_file.exists():
        cmd.extend(['--add-data', f'VERSION{separator}.'])

    print("Starting PyInstaller...")
    print(f"Done! Executable file: {root_dir / 'dist' / 'MedicalApp.exe'}")

if __name__ == '__main__':
    main()