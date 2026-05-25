# interfaces/gui/gui_window/widgets/custom_date_time_widgets.py

import datetime
from typing import Any, Dict 

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QCalendarWidget, QDateEdit, QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QPushButton, QTimeEdit, QMenu, QApplication, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QDate, QTime, Signal

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu



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


class DateEditWidget(QWidget):
    """Виджет для ввода даты: поле с маской + кнопка календаря."""
    dateChanged = Signal(object)  # сигнал с datetime.date или None
  
    @AppLogger.get_instance(
        name = 'DateEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        parent=None, 
        initial_date=None, 
        config: Dict[str, Any] = None
    ):
        """
        Инициализирует виджет для ввода даты: поле с маской + кнопка календаря.

        :param parent: родительский виджет
        :type parent: PySide6.QtWidgets.QWidget
        :param initial_date: начальная дата
        :type initial_date: datetime.date
        :param config: конфигурация
        :type config: Dict[str, Any]
        :return: None
        :raises: None
        """

        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.line_edit = QLineEdit()
        # Применяем маску из конфигурации или стандартную
        if config and config.get('input_mask'):
            self.line_edit.setInputMask(config['input_mask'])
        else:
            self.line_edit.setInputMask("9999-99-99")

        install_standard_context_menu(self.line_edit, menu_type='line')
        # install_standard_context_menu(self.line_edit, menu_type='date')

        self.line_edit.setText("")
        # self.line_edit.installEventFilter(self)
        layout.addWidget(self.line_edit)

        self.calendar_btn = QPushButton("📅")
        self.calendar_btn.setFixedSize(25, 25)
        self.calendar_btn.clicked.connect(self.show_calendar)
        layout.addWidget(self.calendar_btn)

        if initial_date:
            self.set_date(initial_date)

        self.line_edit.textChanged.connect(self._on_text_changed)

    @AppLogger.get_instance(
        name = 'DateEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def set_date(self, d: datetime.date):
    #     if d is None:
    #         self.date_edit.setDateTime(QDateTime())
    #     else:
    #         self.date_edit.setDate(QDate(d.year, d.month, d.day))
    def set_date(self, d: datetime.date):
        if d is None:
            self.line_edit.setText("")
        else:
            self.line_edit.setText(d.isoformat())


    @AppLogger.get_instance(
        name = 'DateEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def get_date(self):
    #     qdate = self.date_edit.date()
    #     if qdate.isValid():
    #         return datetime.date(qdate.year(), qdate.month(), qdate.day())
    #     return None
    def get_date(self):
        text = self.line_edit.text().strip()
        if not text:
            return None
        

        # # Если текст состоит только из пробелов, дефисов и/или подчёркиваний (неполная дата)
        # if all(c in ' -_' for c in text):
        #     return None

        try:
            return datetime.date.fromisoformat(text)
        except ValueError:
            return None

    @AppLogger.get_instance(
        name = 'DateEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_date_time_changed(self, dt):
        self.dateChanged.emit(self.get_date())

    @AppLogger.get_instance(
        name = 'DateEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_text_changed(self, text):
        self.dateChanged.emit(self.get_date())

    @AppLogger.get_instance(
        name = 'DateEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def show_calendar(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Выберите дату")
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget()
        current = self.get_date()
        if current:
            calendar.setSelectedDate(QDate(current.year, current.month, current.day))
        layout.addWidget(calendar)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        if dialog.exec() == QDialog.Accepted:
            qdate = calendar.selectedDate()
            if qdate.isValid():
                self.set_date(datetime.date(qdate.year(), qdate.month(), qdate.day()))
                self.dateChanged.emit(self.get_date())
        dialog.deleteLater()


class TimeEditWidget(QWidget):
    """Виджет для ввода времени: поле с маской + кнопка выбора."""
    timeChanged = Signal(object)

    @AppLogger.get_instance(
        name = 'TimeEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        parent=None, 
        initial_time=None, 
        config: Dict[str, Any] = None
    ):
        """
        Инициализирует виджет для ввода времени: поле с маской + кнопка выбора.

        :param parent: родительский виджет
        :type parent: PySide6.QtWidgets.QWidget
        :param initial_time: начальное время
        :type initial_time: datetime.time
        :param config: конфигурация
        :type config: Dict[str, Any]
        :return: None
        :raises: None
        """

        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QLineEdit()
        if config and config.get('input_mask'):
            self.line_edit.setInputMask(config['input_mask'])
        else:
            self.line_edit.setInputMask("99:99")
        install_standard_context_menu(self.line_edit, menu_type='line')
        # install_standard_context_menu(self.line_edit, menu_type='time')

        self.line_edit.setText("") 
        layout.addWidget(self.line_edit)

        self.time_btn = QPushButton("⏰")
        self.time_btn.setFixedSize(25, 25)
        self.time_btn.clicked.connect(self.show_time_dialog)
        layout.addWidget(self.time_btn)

        if initial_time:
            self.set_time(initial_time)

        self.line_edit.textChanged.connect(self._on_text_changed)

    @AppLogger.get_instance(
        name = 'TimeEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def set_time(self, t: datetime.time):
        # if t is None:
        #     self.time_edit.setTime(QTime())
        # else:
        #     self.time_edit.setTime(QTime(t.hour, t.minute, 0))
    def set_time(self, t: datetime.time):
        if t is None:
            self.line_edit.setText("")
        else:
            self.line_edit.setText(t.strftime("%H:%M"))

    @AppLogger.get_instance(
        name = 'TimeEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def get_time(self):
    #     qtime = self.time_edit.time()
    #     if qtime.isValid():
    #         return datetime.time(qtime.hour(), qtime.minute())
    #     return None
    def get_time(self):
        text = self.line_edit.text().strip()
        if not text:
            return None
        try:
            return datetime.time.fromisoformat(text)
        except ValueError:
            return None

    @AppLogger.get_instance(
        name = 'TimeEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_time_changed(self, qt):
        self.timeChanged.emit(self.get_time())

    @AppLogger.get_instance(
        name = 'TimeEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_text_changed(self, text):
        self.timeChanged.emit(self.get_time())

    @AppLogger.get_instance(
        name = 'TimeEditWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def show_time_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Выберите время")
        layout = QVBoxLayout(dialog)
        time_edit = QTimeEdit()
        current = self.get_time()
        if current:
            time_edit.setTime(QTime(current.hour, current.minute))
        layout.addWidget(time_edit)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        if dialog.exec() == QDialog.Accepted:
            qtime = time_edit.time()
            if qtime.isValid():
                self.set_time(datetime.time(qtime.hour(), qtime.minute()))
                self.timeChanged.emit(self.get_time())
        dialog.deleteLater()