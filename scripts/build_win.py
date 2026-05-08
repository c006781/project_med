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

    # 1. Проверяем наличие PyInstaller
    if not shutil.which('pyinstaller'):
        print("Error: PyInstaller not installed. Run: pip install pyinstaller")
        sys.exit(1)

    # 2. Проверяем, что входной скрипт существует
    entry_point = root_dir / "main_gui_window.py"
    if not entry_point.exists():
        print(f"Error: Entry script not found at {entry_point}")
        sys.exit(1)
    print(f"Entry script: {entry_point}")

    # 3. Формируем команду PyInstaller
    #    Важно: все опции должны идти ДО указания scriptname
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
        'logging', 'logging.handlers', 'logging.config',
        'sqlalchemy.sql.default', 'sqlalchemy.dialects.sqlite',
        'cryptography', 'cryptography.hazmat.backends.openssl',
        'pydantic', 'pydantic_core',
        'yadisk',
        'dotenv', 'requests',
        'msgpack',
        'click',
        # Ваши внутренние модули (на всякий случай)
        'app.utils.logger.logger',
        'app.config.config_manager.manager',
        'app.database.database',
        'interfaces.gui.gui_window.main',
    ]
    for module in hidden:
        cmd.extend(['--hidden-import', module])

    # Собираем все компоненты PySide6
    cmd.extend(['--collect-all', 'PySide6'])

    cmd.extend(['--collect-data', 'certifi'])

    # Добавляем файл VERSION, если существует
    version_file = root_dir / 'VERSION'
    if version_file.exists():
        cmd.extend(['--add-data', f'VERSION{separator}.'])

    # Добавляем опцию --debug для получения подробного лога
    # cmd.append('--debug')  # Раскомментируйте для детальной отладки

    # 4. В самом конце КОМАНДЫ указываем входной скрипт
    cmd.append(str(entry_point))

    print("Starting PyInstaller with command:")
    print(' '.join(cmd))
    print("-" * 50)

    # 5. Запускаем процесс с выводом в реальном времени
    result = subprocess.run(cmd, capture_output=True, text=True)

    # 6. Выводим stdout и stderr
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    # 7. Проверяем успешность
    if result.returncode != 0:
        print(f"PyInstaller failed with code {result.returncode}")
        sys.exit(result.returncode)

    # 8. Проверяем результат
    exe_path = root_dir / 'dist' / 'MedicalApp.exe'
    if exe_path.exists():
        print(f"Done! Executable file: {exe_path}")
    else:
        print(f"ERROR: Executable file not found at {exe_path}")
        sys.exit(1)

if __name__ == '__main__':
    main()