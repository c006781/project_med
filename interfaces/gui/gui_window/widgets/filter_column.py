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
        "fuzzy": "нечёткий поиск"
    }
    

    @AppLogger.get_instance(
        name='FilterColumnDialog',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(
        self,
        column_title: str,
        column_type: type,
        current_operator: str = None,
        current_value: Any = None,
        current_value2: Any = None,
        unique_values: List[Any] = None,
        parent=None
    ):
        super().__init__(parent)
        self.logger = AppLogger.get_instance(
            name='gui.FilterColumnDialog',
            enable_file_logging='user',
            use_name_in_filename='user'
        )
        self.setWindowTitle(f"Фильтр для столбца «{column_title}»")
        self.setMinimumWidth(400)

        self.column_type = column_type
        self.unique_values = unique_values or []

        # Текущие значения
        self.current_operator = current_operator
        self.current_value = current_value
        self.current_value2 = current_value2

        self._setup_ui()
        self._update_ui_for_operator()
        

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Выбор оператора
        self.op_combo = QComboBox()

        for op_key, op_text in self._OPERATORS.items():
            self.op_combo.addItem(op_text, op_key)

        if self.current_operator:
            idx = self.op_combo.findData(self.current_operator)
            if idx >= 0:
                self.op_combo.setCurrentIndex(idx)

        self.op_combo.currentIndexChanged.connect(self._on_operator_changed)

        # Форма для ввода значений
        self.form_layout = QFormLayout()
        self.value_edit = QLineEdit()
        self.value2_edit = QLineEdit()
        self.between_label = QLabel("и")
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.null_check = QCheckBox("NULL (пустое значение)")

        # Специальные виджеты для дат/времени
        if self.column_type == datetime.date:
            self.value_edit = QDateEdit()
            self.value_edit.setCalendarPopup(True)
            self.value_edit.setDisplayFormat("yyyy-MM-dd")
            self.value2_edit = QDateEdit()
            self.value2_edit.setCalendarPopup(True)
            self.value2_edit.setDisplayFormat("yyyy-MM-dd")
        elif self.column_type == datetime.time:
            self.value_edit = QTimeEdit()
            self.value_edit.setDisplayFormat("HH:mm")
            self.value2_edit = QTimeEdit()
            self.value2_edit.setDisplayFormat("HH:mm")
        elif self.column_type == int:
            self.value_edit = QSpinBox()
            self.value_edit.setRange(-9999999, 9999999)
            self.value2_edit = QSpinBox()
            self.value2_edit.setRange(-9999999, 9999999)
        elif self.column_type == float:
            self.value_edit = QLineEdit()
            self.value_edit.setValidator(QDoubleValidator())
            self.value2_edit = QLineEdit()
            self.value2_edit.setValidator(QDoubleValidator())

        self.form_layout.addRow("Оператор:", self.op_combo)
        self.form_layout.addRow(self.value_edit)
        self.form_layout.addRow(self.between_label, self.value2_edit)
        self.form_layout.addRow(self.list_widget)
        self.form_layout.addRow(self.null_check)

        layout.addLayout(self.form_layout)

        # Кнопки OK/Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_ui_for_operator()

    def _on_operator_changed(self):
        self._update_ui_for_operator()

    def _update_ui_for_operator(self):
        op_key = self.op_combo.currentData()
        # Скрываем все, потом покажем нужное
        self.value_edit.setVisible(False)
        self.value2_edit.setVisible(False)
        self.between_label.setVisible(False)
        self.list_widget.setVisible(False)
        self.null_check.setVisible(False)

        if op_key == "between":
            self.value_edit.setVisible(True)
            self.value2_edit.setVisible(True)
            self.between_label.setVisible(True)
        elif op_key == "in":
            self.list_widget.setVisible(True)
            self._populate_list_widget()
        elif op_key in ("is_null", "is_not_null"):
            self.null_check.setVisible(True)
            self.null_check.setText("NULL (пустое значение)" if op_key == "is_null" else "NOT NULL (не пустое)")
            self.null_check.setChecked(True)
        else:
            self.value_edit.setVisible(True)

    def _populate_list_widget(self):
        self.list_widget.clear()
        for val in self.unique_values:
            item = QListWidgetItem(str(val))
            item.setData(Qt.UserRole, val)
            self.list_widget.addItem(item)
        if self.current_operator == "in" and isinstance(self.current_value, list):
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.UserRole) in self.current_value:
                    item.setSelected(True)

    def get_filter(self) -> Tuple[str, Any, Any]:
        """Возвращает (operator, value, value2)."""
        op_key = self.op_combo.currentData()
        value = None
        value2 = None

        if op_key == "between":
            value = self._get_widget_value(self.value_edit)
            value2 = self._get_widget_value(self.value2_edit)
        elif op_key == "in":
            selected = []
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).isSelected():
                    selected.append(self.list_widget.item(i).data(Qt.UserRole))
            value = selected
        elif op_key in ("is_null", "is_not_null"):
            value = None
        else:
            value = self._get_widget_value(self.value_edit)

        return op_key, value, value2

    def _get_widget_value(self, widget):
        if isinstance(widget, QDateEdit):
            qdate = widget.date()
            if qdate.isValid():
                return datetime.date(qdate.year(), qdate.month(), qdate.day())
            return None
        if isinstance(widget, QTimeEdit):
            qtime = widget.time()
            if qtime.isValid():
                return datetime.time(qtime.hour(), qtime.minute())
            return None
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QLineEdit):
            text = widget.text().strip()
            if not text:
                return None
            if self.column_type == int:
                try:
                    return int(text)
                except:
                    return None
            if self.column_type == float:
                try:
                    return float(text)
                except:
                    return None
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
        "fuzzy": "похоже на"
    }

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

    def update_filters(self, filters: Dict[int, Dict[str, Any]], column_titles: Dict[int, str]):
        """Обновляет строку фильтров на основе активных фильтров из прокси-модели."""
        # Удаляем все чипы
        while self.chips_layout.count() > 1:
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not filters:
            self.setVisible(False)
            return

        for col, filter_info in filters.items():
            if filter_info.get('active', False):
                chip = self._create_chip(col, filter_info, column_titles.get(col, f"Столбец {col}"))
                self.chips_layout.insertWidget(self.chips_layout.count() - 1, chip)

        self.setVisible(len(filters) > 0)

    def _create_chip(self, column: int, filter_info: dict, column_title: str) -> QPushButton:
        """Создаёт кнопку-чип для одного фильтра."""
        op = filter_info.get('operator')
        value = filter_info.get('value')
        value2 = filter_info.get('value2')

        # Формируем текст
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

        chip = QPushButton(f"✖ {text}")
        chip.setFlat(True)
        chip.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                border-radius: 12px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)
        chip.setCursor(Qt.PointingHandCursor)
        # При клике на кнопку удаляем фильтр
        chip.clicked.connect(lambda checked, col=column: self.filter_removed.emit(col))
        # Двойной клик – редактировать
        chip.mouseDoubleClickEvent = lambda event: self.filter_edit_requested.emit(column)
        return chip        