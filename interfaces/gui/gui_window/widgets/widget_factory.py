# interfaces/gui/gui_window/widgets/widget_factory.py

"""
Фабрика для создания стандартных виджетов Qt, используемых в динамических формах.
Содержит статические методы, возвращающие готовые виджеты с заданными параметрами.
"""

# import datetime
from typing import Any, Dict

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu

from interfaces.gui.gui_window.widgets.completer_edit import CompleterEdit
from interfaces.gui.gui_window.widgets.custom_date_time_widgets import ( 
    CustomDateEdit, CustomTimeEdit, DateEditWidget, TimeEditWidget
)
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

# from .completer_edit import CompleterEdit
# from .photo_uploader_widget import PhotoUploaderWidget

from PySide6.QtWidgets import (
    QLineEdit, QTextEdit, 
    # QDateEdit, QTimeEdit,
    QSpinBox, QCheckBox, QComboBox, QWidget
)
from PySide6.QtCore import QDate, QTime

from PySide6.QtGui import QTextOption




class WidgetFactory:
    """
    Фабрика, предоставляющая методы для создания типовых виджетов.
    Все методы статические, не требуют создания экземпляра.
    """

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_date_picker_widget(
        editable: bool,
        config: Dict[str, Any] = None
    ) -> QWidget:
        """
        Создаёт виджет для ввода даты с маской и кнопкой календаря.
        Используется как в таблице, так и в форме редактирования.
        """
        # from .custom_date_time_widgets import DateEditWidget
        widget = DateEditWidget(config=config)
        widget.setEnabled(editable)
        return widget

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_time_picker_widget(editable: bool, config: Dict[str, Any] = None) -> QWidget:
        """
        Создаёт виджет для ввода времени с маской и кнопкой выбора.
        Используется как в таблице, так и в форме редактирования.
        """
        # from .custom_date_time_widgets import TimeEditWidget
        widget = TimeEditWidget(config=config)
        widget.setEnabled(editable)
        return widget
    
    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_autocomplete_widget(editable: bool, config: Dict[str, Any] = None)-> QWidget:
        """
        Создаёт CompleterEdit без кнопок (только поле с автодополнением).
        Используется для полей с autocomplete=True.
        """
        # from .completer_edit import CompleterEdit
        widget = CompleterEdit(parent=None, with_create=False, with_edit=False)
        if config and config.get('input_mask'):
            WidgetFactory._apply_mask(widget.line_edit, config)

        install_standard_context_menu(widget.line_edit, menu_type='line')
        widget.setEnabled(editable)
        
        return widget
    

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_mask(widget: QLineEdit, config: Dict[str, Any]) -> None:
        """Устанавливает маску ввода, если она задана в конфигурации."""
        mask = config.get('input_mask')
        if mask:
            widget.setInputMask(mask)

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_text_widget(
        widget_type: str,
        editable: bool,
        config: Dict[str, Any] = None
    ) -> QWidget:
        """
        Создаёт текстовый виджет: QLineEdit (обычное поле) или QTextEdit (многострочное).

        :param widget_type: 'textarea' для QTextEdit, иначе QLineEdit
        :param editable: если False, виджет будет отключён
        :param config: словарь конфигурации поля (может содержать 'input_mask'

        :return: QLineEdit или QTextEdit
        
        """
        if widget_type == 'textarea':
            w = QTextEdit()
            install_standard_context_menu(w, menu_type='text')
            w.setMaximumHeight(200)   # ограничиваем высоту для многострочного поля

            # Включаем перенос слов, чтобы отображать многострочный текст
            # Настройка переноса слов (чтобы длинные слова переносились, а строки не обрезались)
            w.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            # Убедиться, что перенос строк включён (по умолчанию включён, но явно не помешает)
            w.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        else:
            w = QLineEdit()
            if config and config.get('input_mask'):
                WidgetFactory._apply_mask(w, config)
            install_standard_context_menu(w, menu_type='line')

        # install_standard_context_menu(w)
        w.setEnabled(editable)
        
        return w

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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

        install_standard_context_menu(widget.line_edit, menu_type='line')
        widget.setEnabled(editable)

        return widget

    @staticmethod
    @AppLogger.get_instance(
        name='WidgetFactory',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_photo_uploader_widget():
        """
        Создаёт виджет для загрузки фотографий.

        :return: PhotoUploaderWidget
        """
        return PhotoUploaderWidget()