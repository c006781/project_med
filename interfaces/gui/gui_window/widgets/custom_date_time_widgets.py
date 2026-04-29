# interfaces/gui/gui_window/widgets/custom_date_time_widgets.py

import datetime 

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QDateEdit, QTimeEdit, QMenu, QApplication
from PySide6.QtCore import Qt, QDate, QTime



class CustomDateEdit(QDateEdit):
    """QDateEdit с русским контекстным меню (копировать, вставить)."""

    @AppLogger.get_instance(
        name = 'CustomDateEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        """
        Инициализирует CustomDateEdit.
        
        :param parent: родительский виджет
        :type parent: PySide6.QtWidgets.QWidget
        """
        super().__init__(parent)
        self.setCalendarPopup(True)  # поведение
        self.setDisplayFormat("yyyy-MM-dd") # внешний вид
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    @AppLogger.get_instance(
        name = 'CustomDateEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_context_menu(self, pos):
        """
        Показывает контекстное меню для виджета даты.

        :param pos: позиция мыши на экране виджета
        :type pos: QPoint
        :return: None
        :raises: None
        """
        menu = QMenu(self)

        copy_action = menu.addAction("Копировать")
        copy_action.triggered.connect(self._copy_date)
        copy_action.setEnabled(True)

        paste_action = menu.addAction("Вставить")
        paste_action.triggered.connect(self._paste_date)
        has_text = bool(QApplication.clipboard().text())
        paste_action.setEnabled(has_text)

        menu.addSeparator()
        
        select_all_action = menu.addAction("Выделить всё")
        select_all_action.triggered.connect(self.selectAll)
        select_all_action.setEnabled(True)

        menu.exec(self.mapToGlobal(pos))
        
    @AppLogger.get_instance(
        name = 'CustomDateEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _copy_date(self):
        """
        Копирует дату из виджета в буфер обмена.
        :return: None
        :raises: None
        """
        qdate = self.date()
        if qdate.isValid():
            date_str = qdate.toString("yyyy-MM-dd")
            QApplication.clipboard().setText(date_str)
        
    @AppLogger.get_instance(
        name = 'CustomDateEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _paste_date(self):
        """
        Вставляет дату из буфера обмена.

        :raises ValueError: если текст не может быть преобразован в datetime.date
        """
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        try:
            d = datetime.date.fromisoformat(text)
            self.setDate(QDate(d.year, d.month, d.day))
        except ValueError:
            pass


class CustomTimeEdit(QTimeEdit):
    """QTimeEdit с русским контекстным меню (копировать, вставить)."""
        
    @AppLogger.get_instance(
        name = 'CustomTimeEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        """
        Инициализирует QTimeEdit с русским контекстным меню (копировать, вставить).
        
        :param parent: родительский виджет
        :type parent: PySide6.QtWidgets.QWidget
        :return: None
        :raises: None
        """
        super().__init__(parent)
        self.setDisplayFormat("HH:mm")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
    @AppLogger.get_instance(
        name = 'CustomTimeEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_context_menu(self, pos):
        """
        Показывает контекстное меню для виджета времени.

        :param pos: позиция мыши на экране виджета
        :type pos: QPoint
        :return: None
        :raises: None
        """
        menu = QMenu(self)

        copy_action = menu.addAction("Копировать")
        copy_action.triggered.connect(self._copy_time)
        copy_action.setEnabled(True)

        paste_action = menu.addAction("Вставить")
        paste_action.triggered.connect(self._paste_time)
        has_text = bool(QApplication.clipboard().text())
        paste_action.setEnabled(has_text)

        menu.addSeparator()

        select_all_action = menu.addAction("Выделить всё")
        select_all_action.triggered.connect(self.selectAll)
        select_all_action.setEnabled(True)

        menu.exec(self.mapToGlobal(pos))
        
    @AppLogger.get_instance(
        name = 'CustomTimeEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _copy_time(self):
        """
        Копирует время из виджета в буфер обмена.

        :return: None
        :raises: None
        """
        qtime = self.time()
        if qtime.isValid():
            time_str = qtime.toString("HH:mm")
            QApplication.clipboard().setText(time_str)
        
    @AppLogger.get_instance(
        name = 'CustomTimeEdit',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _paste_time(self):
        """
        Вставляет время из буфера обмена.

        :raises ValueError: если текст не может быть преобразован в datetime.time
        """
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        try:
            t = datetime.time.fromisoformat(text)
            self.setTime(QTime(t.hour, t.minute))
        except ValueError:
            pass