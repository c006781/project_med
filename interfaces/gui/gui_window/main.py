#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа в графическое приложение.
Запускает главное окно, инициализирует необходимые компоненты.
"""
import sys
import os

# Добавляем корень проекта в sys.path, чтобы импортировать app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from interfaces.gui.gui_window.main_window import MainWindow

@AppLogger.get_instance(
        name = 'system'
).log_execution_time(
    description="main",
    level = AppLogger._parse_log_level(
        # 'INFO'
        'DEBUG'
    )
)
def main():
    """Главная функция запуска GUI."""
    # Настройка High DPI (для Windows)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Загружаем стили (если есть)
    # with open("interfaces/gui_window/resources/styles.qss", "r") as f:
    #     app.setStyleSheet(f.read())

    # Создаём главное окно
    window = MainWindow()
    window.show()

    # Логируем запуск
    logger = AppLogger.get_instance("gui")
    logger.info("GUI приложение запущено")

    sys.exit(app.exec())

if __name__ == "__main__":
    main()