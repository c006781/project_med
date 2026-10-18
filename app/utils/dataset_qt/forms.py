# app/utils/dataset_qt/forms.py

"""
Форма по описанию полей набора: подпись — из ``FieldDef.label``, виджет — по типу поля,
привязка — ``bind``. Своих форм под каждую таблицу писать не нужно.

Виджет выбирается так (можно задать явно: ``FieldDef.extra['widget']``):

| Поле | Виджет |
|---|---|
| ``BOOLEAN`` | ``QCheckBox`` |
| ``DATE`` / ``DATETIME`` | ``QDateEdit`` / ``QDateTimeEdit`` (календарь; минимальная дата — «пусто») |
| ``INTEGER`` / ``FLOAT`` | ``QSpinBox`` / ``QDoubleSpinBox`` |
| ``TEXT`` | ``QPlainTextEdit`` |
| ``extra['choices']`` (список «значение, подпись») | ``QComboBox`` |
| ``extra['widget'] == 'image'`` | ``QLabel`` с картинкой (байты или путь) |
| остальное | ``QLineEdit`` |

Только для чтения (вычисляемые, итоги, ``read_only``) — тот же виджет без права правки.

Зависит только от PySide6 и ядра ``dataset``.

Пример:
    >>> form = build_form(DataSource(patients), ['last_name', 'birth_date', 'description_text'])
    >>> layout.addLayout(form.layout)
    >>> form.widgets['birth_date']
    <PySide6.QtWidgets.QDateEdit ...>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QSpinBox, QWidget,
)

from .bindings import Binding, bind

try:  # пакеты лежат рядом в одном родительском пакете (как в этом проекте)
    from ..dataset import DataSource, FieldDef, FieldKind
except ImportError:  # pragma: no cover
    from dataset import DataSource, FieldDef, FieldKind

# «Пустая» дата в виджетах дат — минимальная (Binding показывает её как «—»)
NULL_DATE = QDate(1900, 1, 1)


def widget_kind(definition: FieldDef) -> str:
    """
    Вид виджета поля: явный (``extra['widget']``) или по типу.

    Args:
        definition: Описание поля.

    Returns:
        ``'check'``, ``'date'``, ``'datetime'``, ``'int'``, ``'float'``, ``'text'``,
        ``'combo'``, ``'image'`` или ``'line'``.

    Пример:
        >>> widget_kind(FieldDef('birth', kind=FieldKind.DATE))
        'date'
    """
    explicit = (definition.extra or {}).get('widget')
    if explicit:
        return explicit
    if (definition.extra or {}).get('choices'):
        return 'combo'
    return {
        FieldKind.BOOLEAN: 'check', FieldKind.DATE: 'date', FieldKind.DATETIME: 'datetime',
        FieldKind.INTEGER: 'int', FieldKind.FLOAT: 'float', FieldKind.TEXT: 'text',
    }.get(definition.kind, 'line')


def widget_for(definition: FieldDef, parent: Optional[QWidget] = None) -> QWidget:
    """
    Виджет для поля (без привязки).

    Args:
        definition: Описание поля.
        parent: Родитель Qt.

    Returns:
        Виджет.

    Пример:
        >>> isinstance(widget_for(FieldDef('note', kind=FieldKind.TEXT)), QPlainTextEdit)
        True
    """
    kind = widget_kind(definition)
    if kind == 'check':
        return QCheckBox(parent)
    if kind == 'date':
        widget = QDateEdit(parent)
        widget.setCalendarPopup(True)
        widget.setMinimumDate(NULL_DATE)
        widget.setDisplayFormat('dd.MM.yyyy')
        return widget
    if kind == 'datetime':
        widget = QDateTimeEdit(parent)
        widget.setCalendarPopup(True)
        widget.setMinimumDateTime(QDateTime(NULL_DATE, QTime(0, 0)))
        widget.setDisplayFormat('dd.MM.yyyy HH:mm')
        return widget
    if kind == 'int':
        widget = QSpinBox(parent)
        widget.setRange(-2_147_483_647, 2_147_483_647)
        return widget
    if kind == 'float':
        widget = QDoubleSpinBox(parent)
        widget.setRange(-1e12, 1e12)
        widget.setDecimals(int((definition.extra or {}).get('decimals', 2)))
        return widget
    if kind == 'text':
        widget = QPlainTextEdit(parent)
        widget.setMaximumHeight(int((definition.extra or {}).get('height', 60)))
        return widget
    if kind == 'combo':
        return QComboBox(parent)
    if kind == 'image':
        widget = QLabel(parent)
        widget.setMinimumSize(160, 120)
        widget.setAlignment(Qt.AlignCenter)
        widget.setFrameShape(QLabel.StyledPanel)
        return widget
    return QLineEdit(parent)


@dataclass
class Form:
    """
    Собранная форма.

    Attributes:
        layout: Раскладка «подпись — виджет».
        widgets: Виджеты по именам полей.
        bindings: Привязки (``unbind()`` — отвязать).

    Пример:
        >>> form.widgets['last_name'].text()
        'Петров'
    """

    layout: QFormLayout
    widgets: Dict[str, QWidget] = field(default_factory=dict)
    bindings: List[Binding] = field(default_factory=list)

    def unbind(self) -> None:
        """
        Отвязывает все виджеты формы от набора.

        Returns:
            None

        Пример:
            >>> form.unbind()
        """
        for binding in self.bindings:
            binding.unbind()


def build_form(source: DataSource, fields: Optional[Sequence[str]] = None, *,
               on_error: Optional[Callable[[str], None]] = None,
               parent: Optional[QWidget] = None) -> Form:
    """
    Форма по описанию полей набора источника.

    Args:
        source: Источник набора.
        fields: Поля по порядку (по умолчанию — видимые поля набора, кроме ключа).
        on_error: Куда сообщать отказ ввода (по умолчанию — подсказка у виджета).
        parent: Родитель виджетов.

    Returns:
        ``Form``.

    Raises:
        ValueError: У источника нет набора.
        KeyError: Поля нет в наборе.

    Пример:
        >>> build_form(DataSource(appointments)).widgets.keys()
        dict_keys(['date', 'reason_text', 'photo_count'])
    """
    dataset = source.dataset
    if dataset is None:
        raise ValueError("у источника нет набора — форму строить не по чему")
    if fields is None:
        fields = [f.name for f in dataset.fields.visible() if f.name != dataset.key_field]
    form = Form(QFormLayout())
    for name in fields:
        definition = dataset.fields[name]
        widget = widget_for(definition, parent)
        options = {'on_error': on_error, 'image': widget_kind(definition) == 'image'}
        if widget_kind(definition) == 'combo':
            choices = definition.extra.get('choices') or ()
            options['choices'] = choices if callable(choices) else list(choices)
        form.bindings.append(bind(widget, source, name, **options))
        form.widgets[name] = widget
        form.layout.addRow(definition.label, widget)
    return form
