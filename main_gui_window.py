# main_gui_window.py

import os
import subprocess
import sys

import interfaces.gui.gui_window.main as main_gui_window

def rename_self_if_needed():
    """Если приложение запущено как MedicalApp_new_*.exe, переименовывает себя и перезапускается."""
    if not getattr(sys, 'frozen', False):
        return
    exe_path = sys.executable
    exe_name = os.path.basename(exe_path)
    if exe_name.startswith("MedicalApp_new_"):
        dir_name = os.path.dirname(exe_path)
        normal_exe = os.path.join(dir_name, "MedicalApp.exe")
        try:
            # Если старый MedicalApp.exe существует (например, не удалился), удаляем его
            if os.path.exists(normal_exe):
                os.remove(normal_exe)
            # Переименовываем себя
            os.rename(exe_path, normal_exe)
            # Запускаем новую версию
            subprocess.Popen([normal_exe])
            sys.exit(0)
        except Exception as e:
            print(f"Ошибка переименования: {e}")
            
if __name__ == '__main__':
    rename_self_if_needed()
    main_gui_window.main() 

