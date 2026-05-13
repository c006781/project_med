# interfaces/gui/gui_window/widgets/dynamic_edit_form.py

"""
Динамическая форма, автоматически создающая виджеты на основе DTO и field_configs.
"""

import datetime
import os
from typing import Dict, Type, List, Union, get_origin, get_args

from app.config.config_manager.manager import get_config_env
from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu
from interfaces.gui.gui_window.widgets.custom_date_time_widgets import DateEditWidget, TimeEditWidget

# Импортируем вынесенные компоненты
from .completer_edit import CompleterEdit
from .photo_uploader_widget import PhotoUploaderWidget
from .widget_factory import WidgetFactory


from pydantic import BaseModel

from PySide6.QtWidgets import (
    QCompleter, QSizePolicy, QWidget, 
    QFormLayout, QLineEdit, 
    QTextEdit, QDateEdit,
    QTimeEdit, QSpinBox, 
    QCheckBox, QComboBox
)
from PySide6.QtCore import QDate, QTime, Signal, Qt



class DynamicEditForm(QWidget):
    """
    Форма, автоматически создающая виджеты для редактирования полей DTO.
    Использует внешнюю конфигурацию field_configs для настройки.
    """

    fieldChanged = Signal(str, object)   # имя поля, новое значение
    
    # Классовый словарь: тип виджета -> (setter, getter, clearer, connector)
    _HANDLERS = {}


    # Словарь для обработки типов полей
    _TYPE_HANDLERS = {
        # str: lambda editable, widget_type=None: WidgetFactory.create_text_widget(widget_type or 'text', editable),
        str: lambda editable, widget_type=None, config=None: WidgetFactory.create_text_widget(widget_type or 'text', editable, config),
        int: lambda editable, **kw: WidgetFactory.create_int_widget(editable),
        # datetime.date: lambda editable, **kw: WidgetFactory.create_date_widget(editable),
        # datetime.time: lambda editable, **kw: WidgetFactory.create_time_widget(editable),

        datetime.date: lambda editable, config=None, **kw: WidgetFactory.create_date_picker_widget(editable, config),
        datetime.time: lambda editable, config=None, **kw: WidgetFactory.create_time_picker_widget(editable, config),
        bool: lambda editable, **kw: WidgetFactory.create_bool_widget(editable),
    }

    # Словарь для специальных случаев (choices, photo_uploader, completer)
    _SPECIAL_HANDLERS = {
        'choices': lambda editable, choices, **kw: WidgetFactory.create_combobox_widget(choices, editable),
        'photo_uploader': lambda editable, **kw: WidgetFactory.create_photo_uploader_widget(),
        'completer': lambda editable, widget_type, **kw: WidgetFactory.create_completer_edit_widget(widget_type, editable),
        # 'autocomplete': lambda editable, **kw: WidgetFactory.create_autocomplete_widget(editable), 
        'autocomplete': lambda editable, config=None, **kw: WidgetFactory.create_autocomplete_widget(editable, config), 
    }

    @classmethod
    def _init_handlers(cls):
        """Инициализирует словарь обработчиков (один раз для всех экземпляров)."""
        if cls._HANDLERS:
            return

        # from .completer_edit import CompleterEdit
        # from .photo_uploader_widget import PhotoUploaderWidget

        cls._HANDLERS = {
            CompleterEdit: (
                # setter
                lambda w, v: w.setText(str(v) if v is not None else ""),
                # getter
                lambda w: w.text() or None,
                # clearer
                lambda w: w.clear(),
                # connector (widget, field_name, callback) -> подключает сигнал
                lambda w, fn, cb: w.line_edit.textChanged.connect(lambda text, n=fn: cb(n, text)),
            ),
            QLineEdit: (
                lambda w, v: w.setText(str(v) if v is not None else ""),
                lambda w: w.text() or None,
                lambda w: w.clear(),
                lambda w, fn, cb: w.textChanged.connect(lambda text, n=fn: cb(n, text)),
            ),
            QTextEdit: (
                lambda w, v: w.setPlainText(str(v) if v is not None else ""),
                lambda w: w.toPlainText() or None,
                lambda w: w.clear(),
                lambda w, fn, cb: w.textChanged.connect(lambda n=fn: cb(n, w.toPlainText())),
            ),
            QDateEdit: (
                lambda w, v: w.setDate(QDate(v.year, v.month, v.day)) if isinstance(v, datetime.date) else None,
                lambda w: datetime.date(w.date().year(), w.date().month(), w.date().day()),
                lambda w: w.setDate(QDate.currentDate()),
                lambda w, fn, cb: w.dateChanged.connect(lambda d, n=fn: cb(n, d)),
            ),
            QTimeEdit: (
                lambda w, v: w.setTime(QTime(v.hour, v.minute)) if isinstance(v, datetime.time) else None,
                lambda w: datetime.time(w.time().hour(), w.time().minute()),
                lambda w: w.setTime(QTime.currentTime()),
                lambda w, fn, cb: w.timeChanged.connect(lambda t, n=fn: cb(n, t)),
            ),
            QSpinBox: (
                lambda w, v: w.setValue(int(v) if v is not None else 0),
                lambda w: w.value(),
                lambda w: w.setValue(0),
                lambda w, fn, cb: w.valueChanged.connect(lambda val, n=fn: cb(n, val)),
            ),
            QCheckBox: (
                lambda w, v: w.setChecked(bool(v)),
                lambda w: w.isChecked(),
                lambda w: w.setChecked(False),
                lambda w, fn, cb: w.stateChanged.connect(lambda state, n=fn: cb(n, state == Qt.Checked)),
            ),
            PhotoUploaderWidget: (
                lambda w, v: w.set_existing_photos(v if v is not None else []),
                lambda w: w.get_existing_photos(),
                lambda w: w.clear(),
                # Для PhotoUploaderWidget сигнал photosChanged уже есть, но мы не подключаем его к fieldChanged,
                # потому что это делается на уровне страницы. Поэтому connector – заглушка.
                lambda w, fn, cb: None,
            ),
            QComboBox: (
                lambda w, v: w.setCurrentIndex(w.findText(str(v))) if v is not None else None,
                lambda w: w.currentText() or None,
                lambda w: w.setCurrentIndex(0),
                lambda w, fn, cb: w.currentTextChanged.connect(lambda text, n=fn: cb(n, text)),
            ),
            DateEditWidget: (
                lambda w, v: w.set_date(v),
                lambda w: w.get_date(),
                lambda w: w.set_date(None),
                lambda w, fn, cb: w.dateChanged.connect(lambda val, n=fn: cb(n, val)),
            ),
            TimeEditWidget: (
                lambda w, v: w.set_time(v),
                lambda w: w.get_time(),
                lambda w: w.set_time(None),
                lambda w, fn, cb: w.timeChanged.connect(lambda val, n=fn: cb(n, val)),
            ),
        }

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )

        self.dto_class = dto_class
        self.field_configs = field_configs or {}
        self.exclude_fields = exclude_fields or []

        self._loading = False   # блокировка сигналов во время загрузки
        self.widgets = {}       # словарь {имя_поля: виджет}

        # Инициализируем классовые обработчики (один раз)
        self._init_handlers()

        self._setup_ui()

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_virtual_widget(self, config, editable):
        """Создаёт виджет для виртуального поля (только для чтения)."""
        widget_type = config.get('widget_type')
        if widget_type == 'textarea':
            w = QTextEdit()
            w.setReadOnly(not editable)
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
        # по умолчанию – просто текст
        w = QLineEdit()
        w.setReadOnly(True)
        return w
    
    # ----------------------------------------------------------------------
    # Вспомогательные методы для работы с типами
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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


    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
            is_hidden = metadata.get('hidden', False) # поле скрыто

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
            
            # install_standard_context_menu(widget)   
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _configure_photo_widgets(self):
        """
        Находит все виджеты PhotoUploaderWidget и устанавливает им путь к хранилищу фотографий.
        """
        # from app.config.config_manager.manager import get_config_env
        # import os

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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_widget_for_field(self, field, field_name, editable, config):
        """
        Создаёт виджет на основе типа поля и конфигурации.
        """

        # Виртуальное поле с вычислением (только для чтения)
        if config.get('virtual') and config.get('compute'):
            return self._create_virtual_widget(config, editable)

        # Определяем реальный тип поля (нужен для решений ниже)
        real_type = self._get_real_type(field.annotation)

        # Выпадающий список (choices)
        choices = config.get('choices')
        # Если есть choices – создаём комбобокс
        if choices:
            return self._SPECIAL_HANDLERS['choices'](
                editable=editable, 
                choices=choices,
            )
        
        # Автодополнение для строковых полей (без кнопок)
        if config.get('autocomplete') and real_type == str:
            return self._SPECIAL_HANDLERS['autocomplete'](
                editable=editable,
                config=config,
            )

        # Специальные типы виджетов
        widget_type = config.get('widget_type')
        if widget_type in self._SPECIAL_HANDLERS:
            return self._SPECIAL_HANDLERS[widget_type](
                editable=editable, 
                widget_type=widget_type,
                config=config,
            )
        
        # # Определяем реальный тип поля
        # real_type = self._get_real_type(field.annotation)# Определяем реальный тип поля

        # Стандартные виджеты по типу данных
        handler = self._TYPE_HANDLERS.get(real_type)
        if handler:
            return handler(
                editable=editable, 
                widget_type=widget_type,
                config=config,
        )

        return None   # Неподдерживаемый тип – пропускаем

    # ----------------------------------------------------------------------
    # Работа со значениями виджетов
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_widget_value(self, widget, value):
        """
        Устанавливает значение в виджет в зависимости от его типа.
        """
        for cls, (setter, _, _, _) in self._HANDLERS.items():
            if isinstance(widget, cls):
                setter(widget, value)
                break

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_widget_value(self, widget):
        """
        Возвращает значение из виджета в зависимости от его типа.
        """
        for cls, (_, getter, _, _) in self._HANDLERS.items():
            if isinstance(widget, cls):
                return getter(widget)
        return None
    
    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_widget(self, widget):
        for cls, (_, _, clearer, _) in self._HANDLERS.items():
            if isinstance(widget, cls):
                clearer(widget)
                break

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_widget_signals(self, widget, field_name):
        """
        Подключает сигнал изменения значения виджета к слоту _on_field_changed.
        """
        for cls, (_, _, _, connector) in self._HANDLERS.items():
            if isinstance(widget, cls):
                connector(widget, field_name, self._on_field_changed)
                break

    # ----------------------------------------------------------------------
    # Публичные методы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear(self):
        """
        Очищает все виджеты формы.
        """
        for widget in self.widgets.values():
            self._clear_widget(widget)

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # from PySide6.QtWidgets import QCompleter
        completer = QCompleter(items)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        widget.setCompleter(completer)

    @AppLogger.get_instance(
        name='DynamicEditForm',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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