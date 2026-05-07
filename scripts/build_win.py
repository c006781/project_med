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
    print(f"Working directory: {os.getcwd()}")

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
    print(f"Command: {' '.join(cmd)}")

    # Запускаем PyInstaller с захватом вывода
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)

    if result.returncode != 0:
        print(f"PyInstaller failed with code {result.returncode}")
        sys.exit(result.returncode)

    # Проверяем, создался ли файл
    exe_path = root_dir / 'dist' / 'MedicalApp.exe'
    if exe_path.exists():
        print(f"Done! Executable file: {exe_path}")
    else:
        print(f"ERROR: Executable file not found at {exe_path}")
        # Выводим содержимое папки dist, если она существует
        dist_dir = root_dir / 'dist'
        if dist_dir.exists():
            print(f"Contents of {dist_dir}:")
            for f in dist_dir.iterdir():
                print(f"  {f.name}")
        else:
            print("dist directory does not exist")
        sys.exit(1)

if __name__ == '__main__':
    main()