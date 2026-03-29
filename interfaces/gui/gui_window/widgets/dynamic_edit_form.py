# -*- coding: utf-8 -*-
"""
Динамическая форма, автоматически создающая виджеты на основе DTO и field_configs.
"""

import datetime
from typing import Dict, Type, List, Union, get_origin, get_args

from app.utils.logger.logger import AppLogger
from pydantic import BaseModel
from PySide6.QtWidgets import (
    QSizePolicy, QWidget, QFormLayout, QLineEdit, QTextEdit,
    QDateEdit, QTimeEdit, QSpinBox, QCheckBox, QComboBox
)
from PySide6.QtCore import QDate, QTime, Signal, Qt

# Импортируем вынесенные компоненты
from .completer_edit import CompleterEdit
from .photo_uploader_widget import PhotoUploaderWidget
from .widget_factory import WidgetFactory


class DynamicEditForm(QWidget):
    """
    Форма, автоматически создающая виджеты для редактирования полей DTO.
    Использует внешнюю конфигурацию field_configs для настройки.
    """

    fieldChanged = Signal(str, object)   # имя поля, новое значение

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        dto_class: Type[BaseModel],
        parent=None,
        field_configs: Dict[str, Dict] = None,
        exclude_fields: List[str] = None,
    ):
        """
        Инициализирует форму редактирования.

        :param dto_class: класс DTO, используемый для создания записи
        :param parent: родительский виджет
        :param field_configs: словарь конфигурации полей (заголовки, editable, виджеты и т.д.)
        :param exclude_fields: список полей, полностью исключаемых из формы
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='gui.DynamicEditForm',
            enable_file_logging='user',
            use_name_in_filename='system'
        )

        self.dto_class = dto_class
        self.field_configs = field_configs or {}
        self.exclude_fields = exclude_fields or []

        self._loading = False   # блокировка сигналов во время загрузки
        self.widgets = {}       # словарь {имя_поля: виджет}

        self._setup_ui()

    # ----------------------------------------------------------------------
    # Вспомогательные методы для работы с типами
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_real_type(self, annotation):
        """
        Извлекает реальный тип из Union (например, Optional[date] -> date).
        """
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            for arg in args:
                if arg is not type(None):
                    return arg
        return annotation

    # ----------------------------------------------------------------------
    # Подключение сигналов
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_widget_signals(self, widget, field_name):
        """
        Подключает сигнал изменения значения виджета к слоту _on_field_changed.
        """
        if isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda text, n=field_name: self._on_field_changed(n, text))
        elif isinstance(widget, QTextEdit):
            widget.textChanged.connect(lambda n=field_name: self._on_field_changed(n, widget.toPlainText()))
        elif isinstance(widget, QDateEdit):
            widget.dateChanged.connect(lambda date, n=field_name: self._on_field_changed(n, date))
        elif isinstance(widget, QTimeEdit):
            widget.timeChanged.connect(lambda time, n=field_name: self._on_field_changed(n, time))
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(lambda val, n=field_name: self._on_field_changed(n, val))
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(lambda state, n=field_name: self._on_field_changed(n, state == Qt.Checked))
        elif isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(lambda text, n=field_name: self._on_field_changed(n, text))
        # CompleterEdit и PhotoUploaderWidget имеют свои сигналы, но для простоты
        # мы не подключаем их к fieldChanged (это делается при необходимости в странице)
        # Однако для CompleterEdit можно подключить textChanged
        elif isinstance(widget, CompleterEdit):
            widget.line_edit.textChanged.connect(lambda text, n=field_name: self._on_field_changed(n, text))

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_field_changed(self, field_name: str, value):
        """
        Единый слот для всех изменений полей. Испускает сигнал fieldChanged.
        """
        if self._loading:
            return
        self.fieldChanged.emit(field_name, value)

    # ----------------------------------------------------------------------
    # Построение интерфейса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Создаёт форму с помощью QFormLayout, добавляя виджеты для каждого поля DTO.
        """
        layout = QFormLayout(self)
        layout.setSpacing(10)

        fields = self.dto_class.model_fields

        for name, field in fields.items():
            if name in self.exclude_fields:
                continue

            metadata = self.field_configs.get(name, {})
            is_hidden = metadata.get('hidden', False)

            # Заголовок поля
            title = metadata.get('title')
            if title is None:
                title = field.description or name.replace('_', ' ').title()

            editable = metadata.get('editable', True)

            # Создаём виджет
            widget = self._create_widget_for_field(field, name, editable, metadata)

            if widget is None:
                self.logger.warning(f"Не удалось создать виджет для поля {name}")
                continue

            self.widgets[name] = widget

            # Если поле скрыто – не добавляем в layout, но сохраняем в словаре
            if is_hidden:
                continue

            layout.addRow(title + ":", widget)
            self._connect_widget_signals(widget, name)

        # После создания всех виджетов настраиваем photo_uploader (устанавливаем путь к хранилищу)
        self._configure_photo_widgets()

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _configure_photo_widgets(self):
        """
        Находит все виджеты PhotoUploaderWidget и устанавливает им путь к хранилищу фотографий.
        """
        from app.config.config_manager.manager import get_config_env
        import os

        config = get_config_env()
        storage_path = config.get(
            'PHOTOS_STORAGE_PATH',
            os.path.join('.', 'photos')
        )

        for widget in self.widgets.values():
            if isinstance(widget, PhotoUploaderWidget):
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                widget.set_storage_path(storage_path)

    # ----------------------------------------------------------------------
    # Создание виджетов с использованием фабрики
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_widget_for_field(self, field, field_name, editable, config):
        """
        Создаёт виджет на основе типа поля и конфигурации.
        """
        # Виртуальное поле с вычислением (только для чтения)
        if config.get('virtual') and config.get('compute'):
            widget_type = config.get('widget_type')
            if widget_type in ('textarea', 'date', 'time', 'photo_uploader'):
                # Для виртуальных полей с указанным типом создаём соответствующий виджет
                if widget_type == 'textarea':
                    w = QTextEdit()
                    w.setReadOnly(not editable)   # редактируемо, если editable == True
                    w.setMaximumHeight(200)
                    return w
                elif widget_type == 'date':
                    w = QDateEdit()
                    w.setReadOnly(not editable)
                    return w
                elif widget_type == 'time':
                    w = QTimeEdit()
                    w.setReadOnly(not editable)
                    return w
                elif widget_type == 'photo_uploader':
                    return WidgetFactory.create_photo_uploader_widget()
            # По умолчанию – обычное текстовое поле только для чтения
            w = QLineEdit()
            w.setReadOnly(True)
            return w

        widget_type = config.get('widget_type', 'text')
        choices = config.get('choices')

        # Если есть choices – создаём комбобокс
        if choices:
            return WidgetFactory.create_combobox_widget(choices, editable)

        # Специальные типы виджетов
        if widget_type == 'photo_uploader':
            return WidgetFactory.create_photo_uploader_widget()

        if widget_type in ('completer', 'completer_with_create', 'completer_with_edit'):
            return WidgetFactory.create_completer_edit_widget(widget_type, editable)

        # Определяем реальный тип поля
        real_type = self._get_real_type(field.annotation)

        if real_type == str:
            return WidgetFactory.create_text_widget(widget_type, editable)
        elif real_type == int:
            return WidgetFactory.create_int_widget(editable)
        elif real_type == datetime.date:
            return WidgetFactory.create_date_widget(editable)
        elif real_type == datetime.time:
            return WidgetFactory.create_time_widget(editable)
        elif real_type == bool:
            return WidgetFactory.create_bool_widget(editable)

        return None   # Неподдерживаемый тип – пропускаем

    # ----------------------------------------------------------------------
    # Работа со значениями виджетов
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_widget_value(self, widget, value):
        """
        Устанавливает значение в виджет в зависимости от его типа.
        """
        if isinstance(widget, CompleterEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(str(value) if value is not None else "")
        elif isinstance(widget, QDateEdit) and isinstance(value, datetime.date):
            widget.setDate(QDate(value.year, value.month, value.day))
        elif isinstance(widget, QTimeEdit) and isinstance(value, datetime.time):
            widget.setTime(QTime(value.hour, value.minute))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value) if value is not None else 0)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, PhotoUploaderWidget):
            widget.set_existing_photos(value if value is not None else [])
        elif isinstance(widget, QComboBox):
            if value is not None:
                idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_widget_value(self, widget):
        """
        Возвращает значение из виджета в зависимости от его типа.
        """
        if isinstance(widget, CompleterEdit):
            val = widget.text()
            return val if val else None
        elif isinstance(widget, QLineEdit):
            val = widget.text()
            return val if val else None
        elif isinstance(widget, QTextEdit):
            val = widget.toPlainText()
            return val if val else None
        elif isinstance(widget, QDateEdit):
            qdate = widget.date()
            return datetime.date(qdate.year(), qdate.month(), qdate.day())
        elif isinstance(widget, QTimeEdit):
            qtime = widget.time()
            return datetime.time(qtime.hour(), qtime.minute())
        elif isinstance(widget, QSpinBox):
            return widget.value()
        elif isinstance(widget, QCheckBox):
            return widget.isChecked()
        elif isinstance(widget, PhotoUploaderWidget):
            return widget.get_existing_photos()
        elif isinstance(widget, QComboBox):
            return widget.currentText()
        return None

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_value(self, widget):
        """
        Очищает виджет, устанавливая значение по умолчанию.
        """
        if hasattr(widget, 'clear') and callable(widget.clear):
            widget.clear()
        elif isinstance(widget, QDateEdit):
            widget.setDate(QDate.currentDate())
        elif isinstance(widget, QTimeEdit):
            widget.setTime(QTime.currentTime())
        elif isinstance(widget, QSpinBox):
            widget.setValue(0)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(False)
        elif isinstance(widget, QComboBox):
            widget.setCurrentIndex(0)
        elif isinstance(widget, PhotoUploaderWidget):
            widget.clear()

    # ----------------------------------------------------------------------
    # Публичные методы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_data(self, dto: BaseModel):
        """
        Загружает данные из DTO в виджеты формы.
        """
        for name, widget in self.widgets.items():
            value = getattr(dto, name, None)
            if value is not None:
                self._set_widget_value(widget, value)

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_data(self) -> dict:
        """
        Собирает значения из всех виджетов и возвращает словарь.
        """
        data = {}
        for name, widget in self.widgets.items():
            data[name] = self._get_widget_value(widget)
        return data

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear(self):
        """
        Очищает все виджеты формы.
        """
        for widget in self.widgets.values():
            self._clear_value(widget)

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_completer_data(self, field_name: str, items: list):
        """
        Устанавливает QCompleter для поля типа completer.
        """
        widget = self.widgets.get(field_name)
        if not isinstance(widget, CompleterEdit):
            return
        from PySide6.QtWidgets import QCompleter
        completer = QCompleter(items)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        widget.setCompleter(completer)

    @AppLogger.get_instance(
        name='DynamicEditForm',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_photos_data(self, photos):
        """
        Устанавливает существующие фотографии для виджета photo_uploader.
        """
        widget = self.widgets.get('photos')
        if isinstance(widget, PhotoUploaderWidget):
            widget.set_existing_photos(photos)