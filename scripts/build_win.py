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
    root_dir = Path(__file__).parent.parent.resolve()
    os.chdir(root_dir)
    print(f"Working directory: {os.getcwd()}")

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
    ]

    # --- Полный список скрытых импортов ---
    hidden = [
        # logging handlers
        'logging', 'logging.handlers', 'logging.config',
        # sqlalchemy
        'sqlalchemy.sql.default',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.postgresql',
        'sqlalchemy.dialects.mysql',
        'sqlalchemy.dialects.oracle',
        'sqlalchemy.dialects.mssql',
        # cryptography
        'cryptography',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.primitives',
        # pydantic
        'pydantic',
        'pydantic_core',
        'pydantic.networks',
        'pydantic.types',
        # yadisk
        'yadisk',
        # dotenv
        'dotenv',
        # requests
        'requests',
        'requests.packages',
        # msgpack
        'msgpack',
        # click
        'click',
        # alembic (если используется)
        'alembic',
        'alembic.operations',
        # Наши внутренние модули (на всякий случай)
        'app.utils.logger.base_logger',
        'app.utils.logger.logger',
        'app.config.config_manager.manager',
        'app.database.database',
        'app.services.services_all',
        'app.services.sync_service',
        'interfaces.cli.cli',
        'interfaces.gui.gui_window.main',
    ]
    for h in hidden:
        cmd.extend(['--hidden-import', h])

    # Собираем все компоненты PySide6
    cmd.extend(['--collect-all', 'PySide6'])

    # Добавляем файл VERSION, если существует
    version_file = root_dir / 'VERSION'
    if version_file.exists():
        cmd.extend(['--add-data', f'VERSION{separator}.'])

    print("Starting PyInstaller...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    if result.returncode != 0:
        print(f"PyInstaller failed with code {result.returncode}")
        sys.exit(result.returncode)

    exe_path = root_dir / 'dist' / 'MedicalApp.exe'
    if exe_path.exists():
        print(f"Done! Executable file: {exe_path}")
    else:
        print(f"ERROR: Executable file not found at {exe_path}")
        # Выведем содержимое dist для отладки
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