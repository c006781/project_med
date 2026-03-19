# -*- coding: utf-8 -*-
"""
interfaces/gui/gui_window/widgets/dynamic_edit_form.py
(исправленная версия с поддержкой Optional)
"""

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QDateEdit, QTimeEdit,
    QSpinBox, QCheckBox, QComboBox, QTextEdit
)
from PySide6.QtCore import QDate, QTime, Signal, Slot
from typing import Dict, Any, Optional, Type, List, Union, get_origin, get_args
from datetime import date, time
from pydantic import BaseModel


class DynamicEditForm(QWidget):
    """
    Форма, автоматически создающая виджеты для редактирования полей DTO.
    """
    fieldChanged = Signal(str, object)  # имя поля, новое значение

    def __init__(
        self,
        dto_class: Type[BaseModel],
        parent=None,
        exclude_fields: List[str] = None,
        field_editable: Dict[str, bool] = None,
        field_choices: Dict[str, List] = None,
        field_rename: Dict[str, str] = None,
    ):
        super().__init__(parent)
        self.dto_class = dto_class
        self.exclude_fields = exclude_fields or []
        self.field_editable = field_editable or {}
        self.field_choices = field_choices or {}
        self.field_rename = field_rename or {}

        self.widgets = {}
        self._setup_ui()

    def _get_real_type(self, annotation):
        """Извлекает реальный тип из Union (например, Optional[date] -> date)."""
        origin = get_origin(annotation)
        if origin is Union:
            # Берём первый не-None тип
            args = get_args(annotation)
            for arg in args:
                if arg is not type(None):
                    return arg
        return annotation

    def _connect_widget_signals(self, widget, field_name):
        """Подключает соответствующий сигнал виджета к слоту _on_field_changed."""
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

    def _on_field_changed(self, field_name, value):
        """Единый слот для всех изменений полей."""
        self.fieldChanged.emit(field_name, value)

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        fields = self.dto_class.model_fields
        for name, field in fields.items():
            if name in self.exclude_fields:
                continue

            title = self.field_rename.get(name, field.description or name.replace('_', ' ').title())
            editable = self.field_editable.get(name, True)

            widget = self._create_widget_for_field(field, name, editable)
            if widget is None:
                continue

            self.widgets[name] = widget
            layout.addRow(title + ":", widget)

            self._connect_widget_signals(widget, name)

            # # Подключаем сигналы изменения
            # if hasattr(widget, 'textChanged'):
            #     widget.textChanged.connect(lambda val, n=name: self.fieldChanged.emit(n, val))
            # elif hasattr(widget, 'dateChanged'):
            #     widget.dateChanged.connect(lambda val, n=name: self.fieldChanged.emit(n, val))
            # elif hasattr(widget, 'timeChanged'):
            #     widget.timeChanged.connect(lambda val, n=name: self.fieldChanged.emit(n, val))
            # elif hasattr(widget, 'currentTextChanged'):
            #     widget.currentTextChanged.connect(lambda val, n=name: self.fieldChanged.emit(n, val))
            # elif hasattr(widget, 'stateChanged'):
            #     widget.stateChanged.connect(lambda val, n=name: self.fieldChanged.emit(n, val))

    def _create_widget_for_field(self, field, field_name, editable):
        """Создаёт виджет на основе типа поля с учётом Optional."""
        raw_type = field.annotation
        real_type = self._get_real_type(raw_type)

        # Если есть предопределённые значения
        if field_name in self.field_choices:
            combo = QComboBox()
            combo.addItems(self.field_choices[field_name])
            combo.setEditable(False)
            combo.setEnabled(editable)
            return combo

        # Определяем по реальному типу
        if real_type == str:
            if field_name in ('note_text', 'description', 'text'):
                w = QTextEdit()
                w.setMaximumHeight(100)
            else:
                w = QLineEdit()
            w.setEnabled(editable)
            return w

        elif real_type == int:
            w = QSpinBox()
            w.setRange(-999999, 999999)
            w.setEnabled(editable)
            return w

        elif real_type == date:
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDate(QDate.currentDate())
            w.setEnabled(editable)
            return w

        elif real_type == time:
            w = QTimeEdit()
            w.setTime(QTime.currentTime())
            w.setEnabled(editable)
            return w

        elif real_type == bool:
            w = QCheckBox()
            w.setEnabled(editable)
            return w

        return None

    # Остальные методы (load_data, get_data, clear) остаются без изменений
    def load_data(self, dto: BaseModel):
        for name, widget in self.widgets.items():
            value = getattr(dto, name, None)
            if value is None:
                continue
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(str(value))
            elif isinstance(widget, QDateEdit) and isinstance(value, date):
                widget.setDate(QDate(value.year, value.month, value.day))
            elif isinstance(widget, QTimeEdit) and isinstance(value, time):
                widget.setTime(QTime(value.hour, value.minute))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

    def get_data(self) -> dict:
        data = {}
        for name, widget in self.widgets.items():
            if isinstance(widget, QLineEdit):
                data[name] = widget.text() or None
            elif isinstance(widget, QTextEdit):
                data[name] = widget.toPlainText() or None
            elif isinstance(widget, QDateEdit):
                qdate = widget.date()
                data[name] = date(qdate.year(), qdate.month(), qdate.day())
            elif isinstance(widget, QTimeEdit):
                qtime = widget.time()
                data[name] = time(qtime.hour(), qtime.minute())
            elif isinstance(widget, QSpinBox):
                data[name] = widget.value()
            elif isinstance(widget, QCheckBox):
                data[name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                data[name] = widget.currentText()
        return data

    def clear(self):
        for widget in self.widgets.values():
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