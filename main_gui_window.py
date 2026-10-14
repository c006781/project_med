# main_gui_window.py

"""
Точка входа графического приложения (из неё же собирается MedicalApp.exe).

Порядок запуска:
    1. handle_rename_argument() — только в собранном exe после обновления:
       переименовывает exe и перезапускает его.
    2. setup_logging() — передаёт логгерам конфиг. Должен идти ДО main(), иначе
       старт программы не попадёт в лог по настройкам из конфига.
    3. main() — создаёт QApplication и главное окно.

Пример:
    python main_gui_window.py
    MedicalApp.exe --rename-to MedicalApp.exe
"""

import os
import subprocess
import sys
import traceback

import interfaces.gui.gui_window.main as main_gui_window
from app.config.logging_setup import setup_logging

def handle_rename_argument():
    """Если передан аргумент --rename-to, переименовываем текущий exe и перезапускаем."""
    # Работает только в собранном exe
    if not getattr(sys, 'frozen', False):
        return
    
    # Ищем аргумент --rename-to
    rename_to = None
    for i, arg in enumerate(sys.argv):
        if arg == '--rename-to' and i + 1 < len(sys.argv):
            rename_to = sys.argv[i + 1]
            break

    if not rename_to:
        return

    current_exe = sys.executable
    target_exe = os.path.join(os.path.dirname(current_exe), rename_to)
    try:
        # Удаляем старый файл, если он существует (обычно он уже удалён скриптом, но на всякий случай)
        if os.path.exists(target_exe):
            os.remove(target_exe)
            
        # Переименовываем текущий exe
        os.rename(current_exe, target_exe)

        # Удаляем лог обновления, если он есть
        log_path = os.path.join(os.path.dirname(target_exe), "update.log")
        if os.path.exists(log_path):
            os.remove(log_path)

        # Запускаем переименованный exe
        subprocess.Popen([target_exe])
        sys.exit(0)

    except Exception as e:
        # Если не удалось переименовать, лучше показать ошибку и продолжить работу со старым именем
        # import traceback
        traceback.print_exc()
        # Можно также вывести сообщение через QMessageBox, но QApplication ещё не создан.
        # Поэтому просто напечатаем в консоль.
        print(f"Ошибка переименования: {e}", file=sys.stderr)

if __name__ == '__main__':
    handle_rename_argument()

    # Логгеры не читают конфиг сами: передаём его до запуска main(),
    # иначе старт (main [Начало] и всё внутри) пойдёт по настройкам по умолчанию.
    # См. app/utils/logger/IMPLEMENTATION.md §7.1.
    setup_logging()

    main_gui_window.main()

