# interfaces/gui/gui_window/widgets/widget_factory.py

"""
Фабрика для создания стандартных виджетов Qt, используемых в динамических формах.
Содержит статические методы, возвращающие готовые виджеты с заданными параметрами.
"""

import datetime

from app.utils.logger.logger import AppLogger
from interfaces.gui.gui_window.widgets.custom_date_time_widgets import CustomDateEdit, CustomTimeEdit

from .completer_edit import CompleterEdit
from .photo_uploader_widget import PhotoUploaderWidget

from PySide6.QtWidgets import (
    QLineEdit, QTextEdit, QDateEdit, QTimeEdit,
    QSpinBox, QCheckBox, QComboBox
)
from PySide6.QtCore import QDate, QTime




class WidgetFactory:
    """
    Фабрика, предоставляющая методы для создания типовых виджетов.
    Все методы статические, не требуют создания экземпляра.
    """

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_autocomplete_widget(editable: bool):
        """
        Создаёт CompleterEdit без кнопок (только поле с автодополнением).
        Используется для полей с autocomplete=True.
        """
        from .completer_edit import CompleterEdit
        widget = CompleterEdit(parent=None, with_create=False, with_edit=False)
        widget.setEnabled(editable)
        return widget

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_text_widget(widget_type: str, editable: bool):
        """
        Создаёт текстовый виджет: QLineEdit (обычное поле) или QTextEdit (многострочное).

        :param widget_type: 'textarea' для QTextEdit, иначе QLineEdit
        :param editable: если False, виджет будет отключён
        :return: QLineEdit или QTextEdit
        """
        if widget_type == 'textarea':
            w = QTextEdit()
            w.setMaximumHeight(200)   # ограничиваем высоту для многострочного поля
        else:
            w = QLineEdit()

        w.setEnabled(editable)
        return w

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_int_widget(editable: bool):
        """
        Создаёт QSpinBox для целых чисел.

        :param editable: если False, виджет будет отключён
        :return: QSpinBox
        """
        w = QSpinBox()
        w.setRange(-999999, 999999)
        w.setEnabled(editable)
        return w

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_date_widget(editable: bool):
        """
        Создаёт QDateEdit с календарём.

        :param editable: если False, виджет будет отключён
        :return: QDateEdit
        """
        w = CustomDateEdit()
        # w.setCalendarPopup(True)
        w.setDate(QDate.currentDate())   # ← устанавливает текущую дату
        w.setEnabled(editable)
        return w

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_time_widget(editable: bool):
        """
        Создаёт QTimeEdit.

        :param editable: если False, виджет будет отключён
        :return: QTimeEdit
        """
        w = CustomTimeEdit()
        w.setTime(QTime.currentTime())  # ← текущее время
        w.setEnabled(editable)
        return w

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_bool_widget(editable: bool):
        """
        Создаёт QCheckBox.

        :param editable: если False, виджет будет отключён
        :return: QCheckBox
        """
        w = QCheckBox()
        w.setEnabled(editable)
        return w

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_combobox_widget(choices: list, editable: bool):
        """
        Создаёт QComboBox с заданным списком вариантов.

        :param choices: список строк для выпадающего списка
        :param editable: если False, виджет будет отключён
        :return: QComboBox
        """
        combo = QComboBox()
        combo.addItems(choices)
        combo.setEditable(False)
        combo.setEnabled(editable)
        return combo

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_completer_edit_widget(
        widget_type: str, 
        editable: bool,
        with_buttons: bool = True,
    ):
        """
        Создаёт CompleterEdit с возможностью создания/редактирования.

        :param widget_type: 'completer', 'completer_with_create', 'completer_with_edit'
        :param editable: если False, виджет будет отключён
        :param with_buttons: если False, кнопки не добавляются (только поле)
        :return: CompleterEdit
        """

        if widget_type == 'completer' and not with_buttons:
            # Только поле без кнопок
            widget = CompleterEdit(parent=None, with_create=False, with_edit=False)
        else:

            with_create = (widget_type == 'completer_with_create')
            with_edit = (widget_type == 'completer_with_edit')
            widget = CompleterEdit(parent=None, with_create=with_create, with_edit=with_edit)

        widget.setEnabled(editable)
        return widget

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_photo_uploader_widget():
        """
        Создаёт виджет для загрузки фотографий.

        :return: PhotoUploaderWidget
        """
        return PhotoUploaderWidget()