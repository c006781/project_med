# interfaces/gui/gui_window/pages/base_page.py

"""
Базовый класс для всех страниц приложения.
Содержит ссылку на главное окно и менеджер страниц для удобства.
"""

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QWidget


class BasePage(QWidget):
    """
    Базовая страница. Все остальные страницы должны наследовать этот класс.
    """

    @AppLogger.get_instance(
        name = 'BasePage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        """
        Инициализирует базовую страницу.

        :param parent: родительский виджет
        :type parent: Optional[QWidget]
        """
        
        super().__init__(parent)
        # Ссылка на главное окно будет установлена позже
        self.main_window = None
        self.page_manager = None
        self.page_title = "Без названия"

    @AppLogger.get_instance(
        name = 'BasePage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_main_window(self, main_window):
        # """Устанавливает ссылку на главное окно."""
        """
        Устанавливает ссылку на главное окно. Если главное окно
        содержит атрибут page_manager, то он будет установлен
        как атрибут страницы.
        :param main_window: главное окно
        :type main_window: QWidget
        """
        self.main_window = main_window
        # Пробуем получить page_manager из главного окна
        if hasattr(main_window, 'page_manager'):
            self.page_manager = main_window.page_manager

    @AppLogger.get_instance(
        name = 'BasePage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_enter(self):
        """
        Вызывается при переходе на страницу.
        Можно переопределить в наследниках для обновления данных.
        """
        pass

    @AppLogger.get_instance(
        name = 'BasePage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_leave(self):
        """
        Вызывается при уходе со страницы.
        Можно переопределить для сохранения состояния и т.п.
        """
        pass

    @AppLogger.get_instance(
        name = 'BasePage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_page_title(self, title: str):
        """
        Устанавливает заголовок страницы.
        
        :param title: заголовок страницы
        :type title: str
        """
        self.page_title = title

    @AppLogger.get_instance(
        name = 'BasePage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_page_title(self) -> str:
        """
        Возвращает заголовок страницы.
        
        :return: str
        """
        return self.page_title 
        