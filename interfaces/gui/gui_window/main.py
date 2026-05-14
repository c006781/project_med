# interfaces/gui/gui_window/main.py

"""
Точка входа в графическое приложение.
Запускает главное окно, инициализирует необходимые компоненты.
"""
import sys
# import os

# Добавляем корень проекта в sys.path, чтобы импортировать app.*
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.logger.logger import AppLogger

# from interfaces.gui.gui_window.main_window import MainWindow

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt



@AppLogger.get_instance(
    name = 'main.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    description="main",
    level=AppLogger._parse_log_level('DEBUG')
)
def main():
    """Главная функция запуска GUI."""
    # Настройка High DPI (должна быть до создания QApplication)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)

    # Загружаем стили (если есть)
    # with open("interfaces/gui_window/resources/styles.qss", "r") as f:
    #     app.setStyleSheet(f.read())

    # Создаём главное окно

    from interfaces.gui.gui_window.main_window import MainWindow # тут, так как должно быть после создания QApplication
    window = MainWindow()
    window.show()

    # Логируем запуск
    logger = AppLogger.get_instance(
        name = 'gui',
        # share_file_with = 'user',
        enable_file_logging = 'user',
        use_name_in_filename = False, # 'user',
    )
    logger.info("GUI приложение запущено")

    sys.exit(app.exec())

if __name__ == "__main__":
    main()