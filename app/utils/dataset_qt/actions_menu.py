# app/utils/dataset_qt/actions_menu.py

"""
Меню массовых действий над отмеченными строками (по ``ActionSet`` ядра) и окно
«какое поле — какое значение» для действия «задать значение поля».

Меню само следит за набором (через ``DataSource``): доступность пунктов — по
``ActionSet.can_run`` (есть ли отмеченные, можно ли менять набор). Вопрос-подтверждение и
параметры (``Action.params``) спрашиваются окнами; их можно подменить функциями (тесты,
свой экран).

Зависит только от PySide6 и ядра ``dataset``.

Пример:
    >>> menu = ActionsMenu(source, ActionSet(batch=store.batch))
    >>> button = QToolButton(); button.setText('Отмеченные'); button.setMenu(menu)
    >>> button.setPopupMode(QToolButton.InstantPopup)
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QSpinBox, QWidget,
)

from .forms import NULL_DATE, widget_for, widget_kind

try:  # пакеты лежат рядом в одном родительском пакете (как в этом проекте)
    from ..dataset import ActionSet, DataEvent, DataSet, DataSource
except ImportError:  # pragma: no cover
    from dataset import ActionSet, DataEvent, DataSet, DataSource

# Вопрос-подтверждение: (родитель, текст) -> да/нет
Confirm = Callable[[Optional[QWidget], str], bool]
# Вопрос «поле и значение»: (родитель, набор) -> (поле, значение) | None
AskFieldValue = Callable[[Optional[QWidget], DataSet], Optional[Tuple[str, Any]]]


def widget_value(widget: QWidget) -> Any:
    """
    Значение из виджета (того, что строит ``forms.widget_for``).

    Args:
        widget: Виджет.

    Returns:
        Значение (пустая дата/строка — ``None``).

    Пример:
        >>> edit = QLineEdit('А'); widget_value(edit)
        'А'
    """
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QDateEdit):
        return None if widget.date() == NULL_DATE else widget.date().toPython()
    if isinstance(widget, QDateTimeEdit):
        value = widget.dateTime().toPython()
        return None if value.date() == datetime.date(1900, 1, 1) else value
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, QPlainTextEdit):
        return widget.toPlainText() or None
    if isinstance(widget, QLineEdit):
        return widget.text() or None
    return None


class FieldValueDialog(QDialog):
    """
    Окно «какое поле — какое значение» (для «задать значение поля» отмеченным).

    Поля — редактируемые хранимые поля набора; виджет значения — по типу поля.

    Пример:
        >>> dialog = FieldValueDialog(dataset); dialog.exec(); dialog.result_value()
        ('date_next', datetime.date(2026, 11, 1))
    """

    def __init__(self, dataset: DataSet, parent: Optional[QWidget] = None) -> None:
        """
        Args:
            dataset: Набор.
            parent: Родитель Qt.

        Пример:
            >>> FieldValueDialog(ds).fields.count() > 0
            True
        """
        super().__init__(parent)
        self.setWindowTitle('Задать значение поля отмеченным')
        self.dataset = dataset
        layout = QFormLayout(self)
        self.fields = QComboBox()
        for definition in dataset.fields:
            if definition.editable and not definition.local and definition.name != dataset.key_field:
                self.fields.addItem(definition.label, definition.name)
        layout.addRow('Поле', self.fields)
        self.value_holder = QLabel()
        self.value_widget: QWidget = QLineEdit()
        layout.addRow('Значение', self.value_widget)
        self._layout = layout
        self.fields.currentIndexChanged.connect(self._rebuild_value)
        self._rebuild_value()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _rebuild_value(self) -> None:
        """
        Виджет значения — по типу выбранного поля.

        Returns:
            None

        Пример:
            >>> dialog._rebuild_value()
        """
        name = self.fields.currentData()
        if name is None:
            return
        definition = self.dataset.fields[name]
        widget = widget_for(definition, self)
        if widget_kind(definition) == 'combo':
            choices = definition.extra.get('choices') or ()
            widget.addItem('—', None)
            for value, label in (choices() if callable(choices) else choices):
                widget.addItem(str(label), value)
        self._layout.replaceWidget(self.value_widget, widget)
        self.value_widget.deleteLater()
        self.value_widget = widget

    def result_value(self) -> Optional[Tuple[str, Any]]:
        """
        Выбранные поле и значение.

        Returns:
            ``(поле, значение)`` или ``None`` (поле не выбрано).

        Пример:
            >>> dialog.result_value()
            ('phone', '+7 900')
        """
        name = self.fields.currentData()
        return None if name is None else (name, widget_value(self.value_widget))


def ask_field_value(parent: Optional[QWidget], dataset: DataSet) -> Optional[Tuple[str, Any]]:
    """
    Спрашивает окном поле и значение.

    Args:
        parent: Родитель.
        dataset: Набор.

    Returns:
        ``(поле, значение)`` или ``None`` (отказ).

    Пример:
        >>> ask_field_value(window, ds)
        ('date_next', datetime.date(2026, 11, 1))
    """
    dialog = FieldValueDialog(dataset, parent)
    return dialog.result_value() if dialog.exec() == QDialog.Accepted else None


def ask_confirm(parent: Optional[QWidget], text: str) -> bool:
    """
    Вопрос «да/нет» окном.

    Args:
        parent: Родитель.
        text: Вопрос.

    Returns:
        ``True`` — да.

    Пример:
        >>> ask_confirm(window, 'Удалить 3?')
        True
    """
    return QMessageBox.question(parent, 'Отмеченные', text) == QMessageBox.Yes


class ActionsMenu(QMenu):
    """
    Меню массовых действий набора источника.

    Signals:
        error_occurred(str): Действие не удалось.
        done(str, object): Действие выполнено: имя и результат.

    Пример:
        >>> menu = ActionsMenu(source, actions); [a.text() for a in menu.actions()][:2]
        ['Отметить все', 'Снять все отметки']
    """

    error_occurred = Signal(str)
    done = Signal(str, object)

    def __init__(self, source: DataSource, actions: ActionSet, parent: Optional[QWidget] = None, *,
                 confirm: Optional[Confirm] = None, ask_value: Optional[AskFieldValue] = None,
                 title: str = 'Отмеченные') -> None:
        """
        Args:
            source: Источник набора.
            actions: Набор действий.
            parent: Родитель Qt.
            confirm: Вопрос-подтверждение (по умолчанию — окно).
            ask_value: Вопрос «поле — значение» (по умолчанию — окно).
            title: Заголовок меню.

        Пример:
            >>> ActionsMenu(source, ActionSet(), confirm=lambda p, t: True)
        """
        super().__init__(title, parent)
        self.source = source
        self.action_set = actions
        self._confirm = confirm or ask_confirm
        self._ask_value = ask_value or ask_field_value
        self._items: Dict[str, Any] = {}
        self.rebuild()
        source.subscribe(self._on_event)
        self.aboutToShow.connect(self.update_items)

    def rebuild(self) -> None:
        """
        Пункты меню по набору действий (после ``add``/``remove`` действий).

        Returns:
            None

        Пример:
            >>> menu.rebuild()
        """
        self.clear()
        self._items = {}
        group = None
        for action in self.action_set.actions:
            if group is not None and action.group != group:
                self.addSeparator()
            group = action.group
            item = self.addAction(action.label)
            item.setObjectName(f'action_{action.name}')
            item.triggered.connect(lambda checked=False, n=action.name: self.trigger(n))
            self._items[action.name] = item
        self.update_items()

    def item(self, name: str) -> Any:
        """
        Пункт меню по имени действия.

        Args:
            name: Имя.

        Returns:
            ``QAction``.

        Пример:
            >>> menu.item('delete_marked').isEnabled()
            False
        """
        return self._items[name]

    def update_items(self) -> None:
        """
        Доступность пунктов.

        Returns:
            None

        Пример:
            >>> menu.update_items()
        """
        ds = self.source.dataset
        for name, item in self._items.items():
            try:
                item.setEnabled(self.action_set.can_run(name, ds))
            except Exception:
                item.setEnabled(False)

    def _on_event(self, event: DataEvent) -> None:
        """
        Событие набора → доступность пунктов.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> menu._on_event(event)
        """
        self.update_items()

    def trigger(self, name: str) -> Any:
        """
        Запуск действия: подтверждение, параметры, выполнение; ошибка — ``error_occurred``.

        Args:
            name: Имя действия.

        Returns:
            Результат действия или ``None`` (отказ/ошибка).

        Пример:
            >>> menu.trigger('delete_marked')
            2
        """
        ds = self.source.dataset
        action = self.action_set.get(name)
        params: Dict[str, Any] = {}
        try:
            if action.confirm:
                count = len(self.action_set.selection(ds)) if ds is not None else 0
                if not self._confirm(self.parentWidget(), action.confirm.format(count=count)):
                    return None
            if 'field_value' in action.params:
                answer = self._ask_value(self.parentWidget(), ds)
                if answer is None:
                    return None
                params['field'], params['value'] = answer
            result = self.action_set.run(name, ds, **params)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            return None
        finally:
            self.update_items()
        self.done.emit(name, result)
        return result
