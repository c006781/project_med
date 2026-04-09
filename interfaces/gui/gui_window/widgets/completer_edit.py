# interfaces/gui/gui_window/widgets/completer_edit.py

"""
Виджет с полем ввода и опциональной кнопкой для открытия окна редактирования/создания.
Предназначен для полей с автодополнением (например, выбор заметки).
"""


from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PySide6.QtCore import Signal



class CompleterEdit(QWidget):
    """
    Виджет, состоящий из QLineEdit и опциональной кнопки "...".
    Используется для полей, где нужен QCompleter и возможность открыть
    отдельное окно для создания/редактирования связанной сущности.
    """

    # Сигнал, испускаемый при нажатии на кнопку (если она есть)
    button_clicked = Signal()

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, with_create=False, with_edit=False):
        """
        Инициализирует виджет.

        :param parent: родительский виджет (QWidget)
        :param with_create: если True, добавляет кнопку "..." (для создания)
        :param with_edit: если True, добавляет кнопку "..." (для редактирования)
        """
        super().__init__(parent)

        # Создаём горизонтальный layout с отступами 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Поле ввода текста
        self.line_edit = QLineEdit()
        install_standard_context_menu(self.line_edit)
        layout.addWidget(self.line_edit)

        self.btn = None

        # Если нужна кнопка (хотя бы один флаг True)
        if with_create or with_edit:
            self.btn = QPushButton("...")
            self.btn.setMaximumWidth(30)
            layout.addWidget(self.btn)

            # Подключаем сигнал кнопки к сигналу виджета
            self.btn.clicked.connect(self.button_clicked.emit)

    # ----------------------------------------------------------------------
    # Прокси-методы для QLineEdit
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setCompleter(self, completer):
        """Устанавливает QCompleter для поля ввода."""
        self.line_edit.setCompleter(completer)

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def text(self):
        """Возвращает текущий текст из поля ввода."""
        return self.line_edit.text()

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setText(self, text):
        """Устанавливает текст в поле ввода."""
        self.line_edit.setText(text)

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setReadOnly(self, readonly):
        """Устанавливает режим «только чтение» для поля ввода."""
        self.line_edit.setReadOnly(readonly)

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEnabled(self, enabled):
        """
        Включает/отключает виджет и кнопку (если она есть).
        """
        self.line_edit.setEnabled(enabled)
        if self.btn:
            self.btn.setEnabled(enabled)

    @AppLogger.get_instance(
        name='CompleterEdit',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear(self):
        """Очищает текстовое поле."""
        self.line_edit.clear()