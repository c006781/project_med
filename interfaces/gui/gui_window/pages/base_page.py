# -*- coding: utf-8 -*-
"""
Базовый класс для всех страниц приложения.
Содержит ссылку на главное окно и менеджер страниц для удобства.
"""
from PySide6.QtWidgets import QWidget


class BasePage(QWidget):
    """
    Базовая страница. Все остальные страницы должны наследовать этот класс.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Ссылка на главное окно будет установлена позже
        self.main_window = None
        self.page_manager = None

    def set_main_window(self, main_window):
        """Устанавливает ссылку на главное окно."""
        self.main_window = main_window
        # Пробуем получить page_manager из главного окна
        if hasattr(main_window, 'page_manager'):
            self.page_manager = main_window.page_manager

    def on_enter(self):
        """
        Вызывается при переходе на страницу.
        Можно переопределить в наследниках для обновления данных.
        """
        pass

    def on_leave(self):
        """
        Вызывается при уходе со страницы.
        Можно переопределить для сохранения состояния и т.п.
        """
        pass