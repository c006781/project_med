# interfaces/gui/gui_window/widgets/dynamic_edit_form.py


from typing import Dict, Type, List, Union, get_origin, get_args#, Any, Optional

# from datetime import date, time
import datetime 

from app.utils.logger.logger import AppLogger

from pydantic import BaseModel

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QDateEdit, QTimeEdit,
    QSpinBox, QCheckBox, QComboBox, QTextEdit, QHBoxLayout, QPushButton, QCompleter
)
from PySide6.QtCore import QDate, QTime, Signal, Qt#, Slot





class DynamicEditForm(QWidget):
    """
    Форма, автоматически создающая виджеты для редактирования полей DTO.
    Использует внешнюю конфигурацию field_configs для настройки.
    """
    fieldChanged = Signal(str, object)  # имя поля, новое значение

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self,
        dto_class: Type[BaseModel],  # класс DTO, используемый для создания записи
        parent=None,  # родительский виджет
        field_configs: Dict[str, Dict] = None,  # словарь, где ключ - название поля, а значение - словарь с параметрами виджета
        exclude_fields: List[str] = None,  # список полей, исключаемых из формы
        # field_editable: Dict[str, bool] = None,  # словарь, где ключ - название поля, а значение - флаг редактируемости
        # field_choices: Dict[str, List] = None,  # словарь, где ключ - название поля, а значение - список значений для выбора
        # field_rename: Dict[str, str] = None,  # словарь, где ключ - название поля, а значение - новое название поля

    ):
        """
        Инициализирует форму редактирования.
        """
        # вызываем родительский конструктор
        super().__init__(parent)

        # сохраняем параметры инициализации формы
        self.dto_class = dto_class
        self.field_configs = field_configs or {}   # внешняя конфигурация
        self.exclude_fields = exclude_fields or []  # список полей, исключаемых из формы
        # self.field_editable = field_editable or {}  # словарь, где ключ - название поля, а значение - флаг редактируемости
        # self.field_choices = field_choices or {}  # словарь, где ключ - название поля, а значение - список значений для выбора
        # self.field_rename = field_rename or {}  # словарь, где ключ - название поля, а значение - новое название поля

        # создаем словарь для хранения виджетов формы
        self.widgets = {}

        # настраиваем интерфейс формы
        self._setup_ui()

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _get_real_type(self, annotation):
        """
        Извлекает реальный тип из Union (например, Optional[date] -> date).

        Функция работает следующим образом:
        - Если тип является Union, то берется список аргументов (get_args(annotation)).
        - Затем проходимся по списку аргументов и возвращается первый не-None тип.
        - Если тип не является Union, то возвращается сам тип.
        """
        origin = get_origin(annotation)
        if origin is Union:
            # Берём список аргументов
            args = get_args(annotation)
            # Проходимся по списку аргументов и возвращается первый не-None тип
            for arg in args:
                if arg is not type(None):
                    return arg
        # Если тип не является Union, то возвращается сам тип
        return annotation

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_widget_signals(self, widget, field_name):
        """
        Подключает соответствующий сигнал виджета к слоту _on_field_changed.
        
        Это метод берет виджет и имя поля, и подлючает соответствующий сигнал виджета к слоту _on_field_changed.
        Сигнал _on_field_changed срабатывает при изменении значения поля в виджете.
        """
        # Если виджет - это строка ввода (QLineEdit), то подлючаем сигнал textChanged
        if isinstance(widget, QLineEdit):
            # сигнал textChanged отправляется с именем поля и новым значением
            widget.textChanged.connect(lambda text, n=field_name: self._on_field_changed(n, text))
        # Если виджет - это поле ввода текста (QTextEdit), то подлючаем сигнал textChanged
        elif isinstance(widget, QTextEdit):
            # сигнал textChanged отправляется с именем поля
            widget.textChanged.connect(lambda n=field_name: self._on_field_changed(n, widget.toPlainText()))
        # Если виджет - это поле ввода даты (QDateEdit), то подлючаем сигнал dateChanged
        elif isinstance(widget, QDateEdit):
            # сигнал dateChanged отправляется с именем поля и новым значением
            widget.dateChanged.connect(lambda date, n=field_name: self._on_field_changed(n, date))
        # Если виджет - это поле ввода времени (QTimeEdit), то подлючаем сигнал timeChanged
        elif isinstance(widget, QTimeEdit):
            # сигнал timeChanged отправляется с именем поля и новым значением
            widget.timeChanged.connect(lambda time, n=field_name: self._on_field_changed(n, time))
        # Если виджет - это поле ввода целого числа (QSpinBox), то подлючаем сигнал valueChanged
        elif isinstance(widget, QSpinBox):
            # сигнал valueChanged отправляется с именем поля и новым значением
            widget.valueChanged.connect(lambda val, n=field_name: self._on_field_changed(n, val))
        # Если виджет - это поле ввода булевого значения (QCheckBox), то подлючаем сигнал stateChanged
        elif isinstance(widget, QCheckBox):
            # сигнал stateChanged отправляется с именем поля и новым значением
            widget.stateChanged.connect(lambda state, n=field_name: self._on_field_changed(n, state == Qt.Checked))
        # Если виджет - это поле ввода значения из списка (QComboBox), то подлючаем сигнал currentTextChanged
        elif isinstance(widget, QComboBox):
            # сигнал currentTextChanged отправляется с именем поля и новым значением
            widget.currentTextChanged.connect(lambda text, n=field_name: self._on_field_changed(n, text))

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_field_changed(self, field_name: str, value: object):
        """
        Единый слот для всех изменений полей.
        
        Когда изменяется значение поля в виджете, то сигнал fieldChanged
        отправляется с именем поля и новым значением.
        """
        self.fieldChanged.emit(field_name, value)

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """
        Устанавливает интерфейс формы с использованием виджетов,
        соответствующих типам полей DTO.
        """
        # Создаем форму с помощью QFormLayout
        layout = QFormLayout(self)
        layout.setSpacing(10)

        # Получаем список полей DTO
        fields = self.dto_class.model_fields

        # Перебираем все поля
        for name, field in fields.items():
            # проверка на исключение из формы (полное исключение из обработки
            if name in self.exclude_fields:
                continue

            # Получаем метаинформацию о поле
            metadata = self.field_configs.get(name, {})

            # проверяем скрытие поля, если указано в конфигурации
            is_hidden = metadata.get('hidden', False)   

            # Скрытие поля, если указано в конфигурации
            if is_hidden:
                widget = self._create_widget_for_field(field, name, metadata.get('editable', True), metadata)
                if widget is None:
                    continue
                self.widgets[name] = widget
                continue   # не добавляем в layout

            # Заголовок: из конфигурации, либо из description DTO, либо из имени поля
            title = metadata.get('title')
            if title is None:
                title = field.description or name.replace('_', ' ').title()

            # Редактируемость: по умолчанию True, переопределяется конфигурацией
            editable = metadata.get('editable', True)
            
            # Создаем виджет, соответствующий типу поля
            widget = self._create_widget_for_field(field, name, editable, metadata)
            if widget is None:
                continue

            # Добавляем виджет в форму
            self.widgets[name] = widget

            layout.addRow(title + ":", widget)

            # Подключаем сигналы изменения для поля
            self._connect_widget_signals(widget, name)

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _create_widget_for_field(self, field, field_name, editable, config):
        """
        Создает виджет на основе типа поля с учётом Optional.
        
        Если поле является виртуальным или только для чтения, то создаёт QLabel.
        
        Если поле имеет предопределённые значения (choices), то создаёт комбобокс.
        
        Определяем по реальному типу:
        - str: QLineEdit или QTextEdit (если поле является текстом)
        - int: QSpinBox
        - datetime.date: QDateEdit
        - datetime.time: QTimeEdit
        - bool: QCheckBox
        """
        # Берём настройки из внешнего словаря, если есть
        # metadata = config.get(field_name, {})

        # metadata = field.metadata or {}

        # editable: сначала из конфигурации, потом из переданного флага
        # editable = metadata.get('editable', editable)
        
        # Виртуальные поля – только для чтения
        if config.get('virtual') and config.get('compute'):
            # Виртуальное или только для чтения – создаём QLabel
            widget = QLineEdit()
            widget.setReadOnly(True)
            return widget

        widget_type = config.get('widget_type', 'text')

        # Обработка completer-виджетов
        if widget_type in ('completer', 'completer_with_create', 'completer_with_edit'):
            with_create = (widget_type == 'completer_with_create')
            with_edit = (widget_type == 'completer_with_edit')
            widget = CompleterEdit(
                self, 
                with_create=with_create, 
                with_edit=with_edit,
            )
            widget.setEnabled(editable)
            return widget

        # Статический комбобокс (если есть choices)
        choices = config.get('choices')
        if choices:
            combo = QComboBox()
            combo.addItems(choices)
            combo.setEditable(False)
            combo.setEnabled(editable)
            return combo
        
        # По типам
        real_type = self._get_real_type(field.annotation)

        # Определяем по реальному типу
        if real_type == str:
            # if field_name in ('note_text', 'description', 'text'): # Если поле является текстом, то используем QTextEdit с ограничением высоты
            if widget_type == 'textarea':
                w = QTextEdit()
                w.setMaximumHeight(200)
            else:
                # Если поле является строкой, то используем QLineEdit
                w = QLineEdit()
            w.setEnabled(editable)
            return w

        elif real_type == int:
            # Если поле является целым числом, то используем QSpinBox
            w = QSpinBox()
            w.setRange(-999999, 999999)
            w.setEnabled(editable)
            return w

        elif real_type == datetime.date:
            # Если поле является датой, то используем QDateEdit
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDate(QDate.currentDate())
            w.setEnabled(editable)
            return w

        elif real_type == datetime.time:
            # Если поле является временем, то используем QTimeEdit
            w = QTimeEdit()
            w.setTime(QTime.currentTime())
            w.setEnabled(editable)
            return w

        elif real_type == bool:
            # Если поле является булевым значением, то используем QCheckBox
            w = QCheckBox()
            w.setEnabled(editable)
            return w

        return None

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_widget_value(self, widget, value):
        """
        Устанавливает значение в виджет в зависимости от его типа.
        
        Если виджет является строковым полем ввода (QLineEdit),
        то значение из value будет установлено в виде строки.
        
        Если виджет является полем ввода текста (QTextEdit),
        то значение из value будет установлено в виде текста.
        
        Если виджет является полем ввода даты (QDateEdit),
        то значение из value (которое является объектом datetime.date)
        будет установлено в виде даты.
        
        Если виджет является полем ввода времени (QTimeEdit),
        то значение из value (которое является объектом datetime.time)
        будет установлено в виде времени.
        
        Если виджет является полем ввода целого числа (QSpinBox),
        то значение из value (которое является целым числом)
        будет установлено в виде целого числа.
        
        Если виджет является полем ввода булевого значения (QCheckBox),
        то значение из value (которое является булевым значением)
        будет установлено в виде булевого значения.
        
        Если виджет является полем ввода значения из списка (QComboBox),
        то значение из value (которое является строкой)
        будет установлено в виде текста в выбранном элементе списка.
        """

        if isinstance(widget, CompleterEdit):
            widget.setText(str(value))

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
            
        elif isinstance(widget, QComboBox):
            if value is not None:
                idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _get_widget_value(self, widget):
        """
        Возвращает значение из виджета в зависимости от его типа.

        Возвращает None, если значение не может быть получено из виджета.

        Если виджет является полем ввода строки (QLineEdit),
        то возвращается текст из виджета.

        Если виджет является полем ввода многострочного текста (QTextEdit),
        то возвращается текст из виджета.

        Если виджет является полем ввода даты (QDateEdit),
        то возвращается объект datetime.date, содержащий год, месяц и день из виджета.

        Если виджет является полем ввода времени (QTimeEdit),
        то возвращается объект datetime.time, содержащий час и минуту из виджета.

        Если виджет является полем ввода целого числа (QSpinBox),
        то возвращается целое число из виджета.

        Если виджет является полем ввода булевого значения (QCheckBox),
        то возвращается булевое значение из виджета.

        Если виджет является полем ввода значения из списка (QComboBox),
        то возвращается текст из виджета.


        :param widget: виджет формы
        :type widget: QWidget

        """

        if isinstance(widget, CompleterEdit):
            val = widget.text()
            return val if val else None
        
        if isinstance(widget, QLineEdit):
            # возвращает текст из виджета
            val = widget.text()
            # если текст пустой, то возвращает None
            return val if val else None
        
        elif isinstance(widget, QTextEdit):
            # возвращает текст из виджета
            val = widget.toPlainText()
            # если текст пустой, то возвращает None
            return val if val else None
        
        elif isinstance(widget, QDateEdit):
            # возвращает объект datetime.date, содержащий год, месяц и день из виджета
            qdate = widget.date()
            return datetime.date(qdate.year(), qdate.month(), qdate.day())
        
        elif isinstance(widget, QTimeEdit):
            # возвращает объект datetime.time, содержащий час и минуту из виджета
            qtime = widget.time()
            return datetime.time(qtime.hour(), qtime.minute())
        
        elif isinstance(widget, QSpinBox):
            # возвращает целое число из виджета
            return widget.value()
        
        elif isinstance(widget, QCheckBox):
            # возвращает булевое значение из виджета
            return widget.isChecked()
        
        elif isinstance(widget, QComboBox):
            # возвращает текст из виджета

            return widget.currentText()
        else:
            # если тип виджета не подходит под выше условия, то возвращает None
            return None
    
    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _clear_value(self, widget):
        """
        Очищает все виджеты формы, присваивая к ним значения по умолчанию.
        
        Это метод итерирует значение в виджете в зависимости от его типа.
        
        Если виджет является полем ввода строки (QLineEdit), то он очищается.
        
        Если виджет является полем ввода многострочного текста (QTextEdit), то он очищается.
        
        Если виджет является полем ввода даты (QDateEdit), то он устанавливаается на текущую дату.
        
        Если виджет является полем ввода времени (QTimeEdit), то он устанавливаается на текущее время.
        
        Если виджет является полем ввода целого числа (QSpinBox), то он устанавливаается на 0.
        
        Если виджет является полем ввода булевого значения (QCheckBox), то он очищается.
        
        Если виджет является полем ввода значения из списка (QComboBox), то он устанавливаается на первый элемент списка.

        :param widget: виджет формы
        :type widget: QWidget
        :return: None
        :rtype: NoneType
        """

        if isinstance(widget, CompleterEdit):
            widget.clear()

        if isinstance(widget, QLineEdit):
            widget.clear()

        elif isinstance(widget, QTextEdit):
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


        return None

    # --- Публичные методы ---

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def load_data(self, dto: BaseModel):
        """
        Загружает данные из переданного объекта в соответствующие виджеты формы.

        :param dto: объект класса, наследуемого от BaseModel
        :type dto: BaseModel
        """
        for name, widget in self.widgets.items():
            value = getattr(dto, name, None)
            
            if value is None:
                continue

            self._set_widget_value(widget, value)

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_data(self) -> dict:
        """
        Возвращает словарь, содержащий значения из всех виджетов формы.

        :return: словарь с значениями из виджетов формы
        :rtype: dict
        """
        data = {}
        for name, widget in self.widgets.items():
            data[name] = self._get_widget_value(widget)

        return data

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def clear(self):
        """
        Очищает все виджеты формы, присваивая к ним значения по умолчанию.
        """
        for widget in self.widgets.values():
            self._clear_value(widget)

    @AppLogger.get_instance(
        name = 'DynamicEditForm',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_completer_data(self, field_name: str, items: List[str]):
        """
        Устанавливает QCompleter для поля типа completer.
        items – список строк для автодополнения.
        """
        widget = self.widgets.get(field_name)

        if not isinstance(widget, CompleterEdit):
            return
        
        completer = QCompleter(items)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        widget.setCompleter(completer)         


class CompleterEdit(QWidget):
    """
    Виджет с полем ввода и опциональной кнопкой для открытия окна.
    Предназначен для полей с автодополнением.
    """

    button_clicked = Signal()

    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self, 
        parent=None, 
        with_create=False, 
        with_edit=False,
    ):
        """
        Инициализирует виджет.

        :param parent: родительский виджет
        :type parent: QWidget
        :param with_create: флаг, указывающий на то, что кнопка "..." будет добавлена
        :type with_create: bool
        :param with_edit: флаг, указывающий на то, что кнопка "..." будет добавлена
        :type with_edit: bool
        """
        
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.line_edit = QLineEdit()
        layout.addWidget(self.line_edit)

        self.btn = None

        if with_create or with_edit:
            self.btn = QPushButton("...")
            self.btn.setMaximumWidth(30)
            layout.addWidget(self.btn)

            # Сигналы 
            if self.btn:
                self.btn.clicked.connect(self.button_clicked.emit)


    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def setCompleter(self, completer):
        """
        Устанавливает QCompleter для поля ввода.

        :param completer: QCompleter, содержащий список строк для автодополнения
        :type completer: QCompleter
        """
        self.line_edit.setCompleter(completer)

    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def text(self):
        """
        Возвращает текст, который находится в поле ввода.

        :return: текст, который находится в поле ввода
        :rtype: str
        """
        return self.line_edit.text()

    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def setText(self, text):
        """
        Устанавливает текст для поля ввода.

        :param text: текст, который будет установлен в поле ввода
        :type text: str
        """
        self.line_edit.setText(text)

    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def setReadOnly(self, readonly):
        """
        Устанавливает режим только для чтения для поля ввода.

        :param readonly: флаг, указывающий на то, что поле ввода должно быть
            доступно только для чтения
        :type readonly: bool
        """
        self.line_edit.setReadOnly(readonly)

    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def setEnabled(self, enabled):
        """
        Включает/отключает виджет и кнопку, если она есть.

        :param enabled: флаг, указывающий на то, что виджет и кнопка должны быть
            включены или отключены
        :type enabled: bool
        """
        self.line_edit.setEnabled(enabled)
        if self.btn:
            self.btn.setEnabled(enabled)

    @AppLogger.get_instance(
        name = 'CompleterEdit',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def clear(self):
        """
        Очищает текстовое поле ввода.
        """
        self.line_edit.clear()