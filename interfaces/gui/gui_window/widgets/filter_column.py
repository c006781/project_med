# interfaces/gui/gui_window/widgets/filter_column.py

import datetime

from typing import (
    Any, Optional, List, Tuple,
    Dict, Callable
)

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QLabel, QPushButton,
    QDateEdit, QTimeEdit, QSpinBox, QCheckBox, QListWidget,
    QListWidgetItem, QDialogButtonBox,
    QWidget,  QScrollArea, QFrame,
)

from PySide6.QtCore import (
    Signal, Qt, QDate, QTime, Slot
)

from PySide6.QtGui import QDoubleValidator

class FilterColumnDialog(QDialog):
    """Диалог настройки фильтра для одного столбца."""

    _OPERATORS = { # Операторы, которые поддерживаются (можно взять из FilterOperator, но для UI свои строки)
        "eq": "равно",
        "ne": "не равно",
        "gt": "больше",
        "ge": "больше или равно",
        "lt": "меньше",
        "le": "меньше или равно",
        "like": "содержит (LIKE)",
        "ilike": "содержит (без учёта регистра)",
        "in": "в списке",
        "between": "между",
        "is_null": "пусто (NULL)",
        "is_not_null": "не пусто (NOT NULL)",
        # "fuzzy": "нечёткий поиск"
    }

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        column_title: str,
        column_type: type,
        current_logic=None,
        current_conditions=None,
        unique_values: List[Any] = None,
        parent=None
    ):
        super().__init__(parent)
        self.column_title = column_title
        self.column_type = column_type
        self.unique_values = unique_values or []
        self.setWindowTitle(f"Фильтр для столбца «{column_title}»")
        self.setMinimumWidth(500)

        # Текущие значения
        self.current_logic = current_logic if current_logic in ('AND', 'OR') else 'AND'
        self.current_conditions = current_conditions or []

        self._setup_ui()
        self._load_conditions()
       
    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Выбор логики объединения
        logic_layout = QHBoxLayout()
        logic_layout.addWidget(QLabel("Условия объединять через:"))
        self.logic_combo = QComboBox()
        self.logic_combo.addItem("И (AND)", 'AND')
        self.logic_combo.addItem("ИЛИ (OR)", 'OR')
        self.logic_combo.setCurrentIndex(0 if self.current_logic == 'AND' else 1)
        logic_layout.addWidget(self.logic_combo)
        layout.addLayout(logic_layout)

        # Список условий
        self.conditions_widget = QWidget()
        self.conditions_layout = QVBoxLayout(self.conditions_widget)
        self.conditions_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.conditions_widget)
        layout.addWidget(scroll)

        # Кнопка добавления условия
        add_btn = QPushButton("+ Добавить условие")
        add_btn.clicked.connect(self._add_condition)
        layout.addWidget(add_btn)

        # Кнопки OK/Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_conditions(self):
        """Загружает существующие условия в UI."""
        self._clear_conditions()
        if not self.current_conditions:
            self._add_condition()  # одно пустое условие по умолчанию
        else:
            for cond in self.current_conditions:
                self._add_condition(cond)
    
    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )            
    def _clear_conditions(self):
        while self.conditions_layout.count():
            child = self.conditions_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _add_condition(self, condition=None):
        """Добавляет строку редактирования одного условия."""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)

        # Выбор оператора
        op_combo = QComboBox()
        for op_key, op_text in self._OPERATORS.items():
            op_combo.addItem(op_text, op_key)
        if condition:
            idx = op_combo.findData(condition['operator'])
            if idx >= 0:
                op_combo.setCurrentIndex(idx)
        layout.addWidget(op_combo)

        # Виджеты для ввода значений (зависит от оператора)
        value_widget = self._create_value_widget()
        value2_widget = self._create_value_widget()
        between_label = QLabel("и")
        between_label.setVisible(False)
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.MultiSelection)
        list_widget.setVisible(False)
        null_check = QCheckBox("NULL (пустое значение)")
        null_check.setVisible(False)

        layout.addWidget(value_widget)
        layout.addWidget(between_label)
        layout.addWidget(value2_widget)
        layout.addWidget(list_widget)
        layout.addWidget(null_check)

        # Кнопка удаления условия
        del_btn = QPushButton("✖")
        del_btn.setFixedSize(24, 24)
        # del_btn.clicked.connect(lambda: frame.deleteLater())
        del_btn.clicked.connect(lambda: self._remove_condition_frame(frame))
        layout.addWidget(del_btn)

        # Сохраняем ссылки на динамические виджеты в свойствах frame
        frame.op_combo = op_combo
        frame.value_widget = value_widget
        frame.value2_widget = value2_widget
        frame.between_label = between_label
        frame.list_widget = list_widget
        frame.null_check = null_check

        # Функция обновления видимости при смене оператора
        def update_visibility():
            op_key = op_combo.currentData()
            # Скрыть все
            value_widget.setVisible(False)
            value2_widget.setVisible(False)
            between_label.setVisible(False)
            list_widget.setVisible(False)
            null_check.setVisible(False)
            if op_key == "between":
                value_widget.setVisible(True)
                value2_widget.setVisible(True)
                between_label.setVisible(True)
            elif op_key == "in":
                list_widget.setVisible(True)
                self._populate_list_widget(list_widget, self.unique_values)
                # Если есть сохранённое значение, выделить
                if condition and condition.get('operator') == 'in':
                    selected = condition.get('value', [])
                    for i in range(list_widget.count()):
                        item = list_widget.item(i)
                        if item.data(Qt.UserRole) in selected:
                            item.setSelected(True)
            elif op_key in ("is_null", "is_not_null"):
                null_check.setVisible(True)
                null_check.setText("NULL (пустое значение)" if op_key == "is_null" else "NOT NULL (не пустое)")
                null_check.setChecked(condition.get('value') is None if op_key == "is_null" else condition.get('value') is not None)
            else:
                value_widget.setVisible(True)
                # Установить значение из condition, если есть
                if condition and condition.get('operator') == op_key:
                    self._set_widget_value(value_widget, condition.get('value'))
                    if op_key == "between" and condition.get('value2'):
                        self._set_widget_value(value2_widget, condition.get('value2'))

        op_combo.currentIndexChanged.connect(update_visibility)
        update_visibility()

        self.conditions_layout.addWidget(frame)


    def _remove_condition_frame(self, frame):
        self.conditions_layout.removeWidget(frame)
        frame.deleteLater()


    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_value_widget(self):
        """Создаёт виджет для ввода значения в зависимости от column_type."""
        if self.column_type == datetime.date:
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd")
        elif self.column_type == datetime.time:
            w = QTimeEdit()
            w.setDisplayFormat("HH:mm")
        elif self.column_type == int:
            w = QSpinBox()
            w.setRange(-9999999, 9999999)
        elif self.column_type == float:
            w = QLineEdit()
            w.setValidator(QDoubleValidator())
        else:
            w = QLineEdit()
        return w

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_widget_value(self, widget, value):
        if value is None:
            return
        if isinstance(widget, QDateEdit):
            if isinstance(value, datetime.date):
                widget.setDate(QDate(value.year, value.month, value.day))
        elif isinstance(widget, QTimeEdit):
            if isinstance(value, datetime.time):
                widget.setTime(QTime(value.hour, value.minute))
        elif isinstance(widget, QSpinBox):
            widget.setValue(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))

    # @AppLogger.get_instance(
    #     name='FilterColumnDialog',
    #     enable_file_logging='system',
    #     use_name_in_filename='system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _on_operator_changed(self):
    #     self._update_ui_for_operator()

    # @AppLogger.get_instance(
    #     name='FilterColumnDialog',
    #     enable_file_logging='system',
    #     use_name_in_filename='system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _update_ui_for_operator(self):
    #     op_key = self.op_combo.currentData()
    #     # Скрываем все, потом покажем нужное
    #     self.value_edit.setVisible(False)
    #     self.value2_edit.setVisible(False)
    #     self.between_label.setVisible(False)
    #     self.list_widget.setVisible(False)
    #     self.null_check.setVisible(False)

    #     if op_key == "between":
    #         self.value_edit.setVisible(True)
    #         self.value2_edit.setVisible(True)
    #         self.between_label.setVisible(True)
    #     elif op_key == "in":
    #         self.list_widget.setVisible(True)
    #         self._populate_list_widget()
    #     elif op_key in ("is_null", "is_not_null"):
    #         self.null_check.setVisible(True)
    #         self.null_check.setText("NULL (пустое значение)" if op_key == "is_null" else "NOT NULL (не пустое)")
    #         self.null_check.setChecked(True)
    #     else:
    #         self.value_edit.setVisible(True)

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _populate_list_widget(self, list_widget, values):
        list_widget.clear()
        for val in values:
            item = QListWidgetItem(str(val))
            item.setData(Qt.UserRole, val)
            list_widget.addItem(item)

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_filter(self):
        """Возвращает (logic, list_of_conditions)."""
        logic = self.logic_combo.currentData()
        conditions = []
        for i in range(self.conditions_layout.count()):
            frame = self.conditions_layout.itemAt(i).widget()
            if not frame:
                continue
            op_key = frame.op_combo.currentData()
            if op_key == "in":
                selected = []
                for j in range(frame.list_widget.count()):
                    if frame.list_widget.item(j).isSelected():
                        selected.append(frame.list_widget.item(j).data(Qt.UserRole))
                value = selected
                value2 = None
            elif op_key in ("is_null", "is_not_null"):
                value = None
                value2 = None
            elif op_key == "between":
                value = self._get_widget_value(frame.value_widget)
                value2 = self._get_widget_value(frame.value2_widget)
            else:
                value = self._get_widget_value(frame.value_widget)
                value2 = None
            conditions.append({
                'operator': op_key,
                'value': value,
                'value2': value2
            })
        # Фильтруем пустые условия (без значения)
        conditions = [c for c in conditions if not (c['operator'] not in ('is_null', 'is_not_null') and c['value'] is None)]
        return logic, conditions

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_widget_value(self, widget):
        if isinstance(widget, QDateEdit):
            qd = widget.date()
            return datetime.date(qd.year(), qd.month(), qd.day()) if qd.isValid() else None
        
        if isinstance(widget, QTimeEdit):
            qt = widget.time()
            return datetime.time(qt.hour(), qt.minute()) if qt.isValid() else None
        
        if isinstance(widget, QSpinBox):
            return widget.value()
        
        if isinstance(widget, QLineEdit):
            text = widget.text().strip()
            if not text:
                return None
            
            if self.column_type == int:
                try: return int(text)
                except: return None

            if self.column_type == float:
                try: return float(text)
                except: return None

            return text
        
        return None

class FilterBar(QFrame):
    """Строка активных фильтров с чипами."""

    _OPERATOR_NAMES = { # Сопоставление операторов с человеко-читаемыми названиями
        "eq": "=",
        "ne": "≠",
        "gt": ">",
        "ge": "≥",
        "lt": "<",
        "le": "≤",
        "like": "содержит (с учётом регистра)",
        "ilike": "содержит (без учёта регистра)",
        "in": "в",
        "between": "от",
        "is_null": "пусто",
        "is_not_null": "не пусто",
        # "fuzzy": "похоже на"
    }

    filter_condition_removed = Signal(int, int)  # column, condition_index

    filter_removed = Signal(int)          # column index
    all_filters_cleared = Signal()
    filter_edit_requested = Signal(int)   # column index

    @AppLogger.get_instance(
        name='FilterBar',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = AppLogger.get_instance(
            name='gui.FilterBar',
            enable_file_logging='user',
            use_name_in_filename='user'
        )
        self.setVisible(False)  # изначально скрыта
        self.setFrameShape(QFrame.StyledPanel)
        self.setMaximumHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Область прокрутки для чипов
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chips_widget = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_widget)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(5)
        self.chips_layout.addStretch()

        self.scroll.setWidget(self.chips_widget)
        layout.addWidget(self.scroll)

        # Кнопка "Очистить все"
        self.clear_all_btn = QPushButton("✖ Очистить все")
        self.clear_all_btn.setFixedWidth(100)
        self.clear_all_btn.clicked.connect(self.all_filters_cleared.emit)
        layout.addWidget(self.clear_all_btn)

    @AppLogger.get_instance(
        name='FilterBar',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def update_filters(
        self, 
        filters: Dict[int, Dict[str, Any]], 
        column_titles: Dict[int, str]
    ):
        # Очищаем все чипы
        while self.chips_layout.count() > 1:
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not filters:
            self.setVisible(False)
            return

        # Для каждого столбца создаём отдельный чип для каждого условия
        for col, filter_def in filters.items():
            logic = filter_def.get('logic', 'AND')
            conditions = filter_def.get('conditions', [])
            col_title = column_titles.get(col, f"Столбец {col}")
            for idx, cond in enumerate(conditions):
                chip = self._create_chip(col, cond, col_title, idx, len(conditions), logic)
                self.chips_layout.insertWidget(self.chips_layout.count() - 1, chip)
        self.setVisible(True)

    @AppLogger.get_instance(
        name='FilterBar',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_chip(self, column: int, condition: dict, column_title: str, cond_idx: int, total_conds: int, logic: str) -> QPushButton:
        op = condition.get('operator')
        value = condition.get('value')
        value2 = condition.get('value2')
        op_text = self._OPERATOR_NAMES.get(op, op)
        if op == "between":
            text = f"{column_title} {op_text} {value} и {value2}"
        elif op == "in":
            if isinstance(value, list) and len(value) > 2:
                text = f"{column_title} {op_text} {len(value)} значений"
            else:
                text = f"{column_title} {op_text} {value}"
        elif op in ("is_null", "is_not_null"):
            text = f"{column_title} {op_text}"
        else:
            text = f"{column_title} {op_text} {value}"
        if total_conds > 1:
            text = f"[{logic}] {text}"
        chip = QPushButton(f"✖ {text}")
        chip.setFlat(True)
        chip.setStyleSheet(
            """
            QPushButton {
                background-color: #e0e0e0;
                border-radius: 12px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            """
        )
        chip.setCursor(Qt.PointingHandCursor)
        # При клике – удалить конкретное условие
        chip.clicked.connect(lambda checked, col=column, idx=cond_idx: self.filter_condition_removed.emit(col, idx))
        # Двойной клик – редактировать весь фильтр столбца (все условия)
        chip.mouseDoubleClickEvent = lambda event: self.filter_edit_requested.emit(column)
        return chip       