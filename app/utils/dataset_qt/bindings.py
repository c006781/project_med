# app/utils/dataset_qt/bindings.py

"""
Привязка виджетов Qt к полю набора (аналог ``TDBEdit``, ``TDBMemo``, ``TDBCheckBox``,
``TDBLookupComboBox``, ``TDBImage`` RAD Studio).

``bind(виджет, источник, 'поле')`` — и виджет показывает значение поля текущей строки,
а ввод в виджете меняет поле (правка начинается сама, если у источника ``auto_edit``).
Сменилась текущая строка, перечитали набор, поле поменяли в другом месте — виджет
обновился. Поле не редактируется (только чтение, вычисляемое, набор нельзя менять) —
виджет только для чтения.

Поддержано: ``QLineEdit``, ``QPlainTextEdit``, ``QTextEdit``, ``QSpinBox``,
``QDoubleSpinBox``, ``QCheckBox``, ``QDateEdit``, ``QDateTimeEdit``, ``QComboBox``
(список «значение → подпись»), ``QLabel`` (текст или картинка: байты/путь к файлу).

Зависит только от PySide6 и ядра ``dataset``.

Пример:
    >>> bind(ui.last_name, source, 'last_name')
    >>> bind(ui.birth_date, source, 'birth_date')
    >>> bind(ui.doctor, source, 'doctor_id', choices=[(1, 'Иванов'), (2, 'Петрова')])
    >>> bind(ui.photo, source, 'image', image=True)
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Optional, Sequence, Tuple

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDoubleSpinBox, QLabel, QLineEdit,
    QPlainTextEdit, QSpinBox, QTextEdit, QWidget,
)

try:  # пакеты лежат рядом в одном родительском пакете (как в этом проекте)
    from ..dataset import DataEvent, DataSet, DataSource, EventKind
except ImportError:  # pragma: no cover
    from dataset import DataEvent, DataSet, DataSource, EventKind

# После каких событий виджет перечитывает значение
_REFRESH_EVENTS = frozenset({
    EventKind.OPENED, EventKind.CLOSED, EventKind.REFRESHED, EventKind.CURRENT_CHANGED,
    EventKind.STATE_CHANGED, EventKind.ROWS_REMOVED,
})

ErrorHandler = Callable[[str], None]


class Binding:
    """
    Связь одного виджета с полем.

    Attributes:
        widget: Виджет.
        source: Источник набора.
        field: Имя поля.

    Пример:
        >>> b = bind(edit, source, 'name'); b.unbind()
    """

    def __init__(self, widget: QWidget, source: DataSource, field: str, *,
                 choices: Optional[Sequence[Tuple[Any, str]]] = None, image: bool = False,
                 on_error: Optional[ErrorHandler] = None) -> None:
        """
        Args:
            widget: Виджет (см. поддержанные в описании модуля).
            source: Источник набора.
            field: Имя поля.
            choices: Для ``QComboBox`` — список ``(значение, подпись)`` или функция,
                возвращающая его (перечитывается при обновлении виджета).
            image: Для ``QLabel`` — показывать картинку (байты/путь), а не текст.
            on_error: Куда сообщать отказ (поле не прошло, набор нельзя менять);
                по умолчанию — подсказка у виджета.

        Raises:
            TypeError: Виджет не поддержан.

        Пример:
            >>> Binding(QLineEdit(), source, 'name')
            <Binding QLineEdit→name>
        """
        self.widget, self.source, self.field = widget, source, field
        self._image = image
        self._on_error = on_error
        self._updating = False
        # список выбора: готовый или функция (перечитывается при каждом обновлении —
        # например, ссылка на таблицу, куда добавили новую несохранённую запись)
        self._choices = choices
        self._shown_choices: Optional[tuple] = None
        if isinstance(widget, QComboBox) and choices is not None:
            self._updating = True
            try:
                self._fill_choices()
            finally:
                self._updating = False
        self._connect_widget()
        source.subscribe(self._on_event)
        self.refresh()

    def __repr__(self) -> str:
        """
        Кратко.

        Returns:
            Строка.

        Пример:
            >>> binding
            <Binding QLineEdit→name>
        """
        return f"<Binding {type(self.widget).__name__}→{self.field}>"

    def _fill_choices(self) -> None:
        """
        Заполняет список выбора ``QComboBox`` (первый пункт «—» — пусто); если список не
        изменился — ничего (не сбивать открытый список).

        Returns:
            None

        Пример:
            >>> binding._fill_choices()
        """
        items = self._choices() if callable(self._choices) else self._choices
        items = tuple((value, str(label)) for value, label in (items or ()))
        if items == self._shown_choices:
            return
        self._shown_choices = items
        w = self.widget
        w.clear()
        w.addItem('—', None)
        for value, label in items:
            w.addItem(label, value)

    # ------------------------------------------------------------------ виджет → поле

    def _connect_widget(self) -> None:
        """
        Подключает сигнал ввода виджета.

        Returns:
            None

        Raises:
            TypeError: Виджет не поддержан.

        Пример:
            >>> binding._connect_widget()
        """
        w = self.widget
        if isinstance(w, QLineEdit):
            w.textEdited.connect(lambda text: self._commit(text))
        elif isinstance(w, (QPlainTextEdit, QTextEdit)):
            w.textChanged.connect(lambda: self._commit(w.toPlainText()))
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.valueChanged.connect(lambda value: self._commit(value))
        elif isinstance(w, QCheckBox):
            w.toggled.connect(lambda checked: self._commit(bool(checked)))
        elif isinstance(w, QDateEdit):              # подкласс QDateTimeEdit — проверять раньше
            w.dateChanged.connect(lambda _: self._commit(self._date_value()))
        elif isinstance(w, QDateTimeEdit):
            w.dateTimeChanged.connect(lambda _: self._commit(self._datetime_value()))
        elif isinstance(w, QComboBox):
            w.currentIndexChanged.connect(lambda _: self._commit(w.currentData()))
        elif isinstance(w, QLabel):
            pass                                      # только показ
        else:
            raise TypeError(f"виджет {type(w).__name__} не поддержан")

    def _date_value(self) -> Optional[datetime.date]:
        """
        Значение ``QDateEdit``: минимальная дата — «пусто».

        Returns:
            Дата или ``None``.

        Пример:
            >>> binding._date_value()
            datetime.date(2026, 10, 18)
        """
        w = self.widget
        if w.date() == w.minimumDate():
            return None
        return w.date().toPython()

    def _datetime_value(self) -> Optional[datetime.datetime]:
        """
        Значение ``QDateTimeEdit``: минимальная — «пусто».

        Returns:
            Дата-время или ``None``.

        Пример:
            >>> binding._datetime_value()
            datetime.datetime(2026, 10, 18, 9, 0)
        """
        w = self.widget
        if w.dateTime() == w.minimumDateTime():
            return None
        return w.dateTime().toPython()

    def _commit(self, value: Any) -> None:
        """
        Ввод в виджете → значение поля текущей строки.

        Args:
            value: Значение из виджета.

        Returns:
            None

        Пример:
            >>> binding._commit('Петров')
        """
        if self._updating:
            return
        ds = self.source.dataset
        if ds is None or not ds.active or ds.current_index < 0:
            return
        if isinstance(self.widget, (QLineEdit, QPlainTextEdit, QTextEdit)) and value == '':
            current = ds.value(self.field)
            value = None if current is None else ''        # стёрли пустое — осталось пустым
        definition = ds.fields.get(self.field)
        local = definition is not None and definition.local
        try:
            # своё поле набора (отметка) — без режима правки: auto_edit к нему не относится
            if not local and not ds.state.editing and not self.source.auto_edit:
                raise PermissionError("правка с экрана выключена (auto_edit)")
            ds.set_value(self.field, value)
        except Exception as exc:
            self._report(str(exc))
            self.refresh()                                 # показать то, что в наборе

    def _report(self, message: str) -> None:
        """
        Сообщает об отказе.

        Args:
            message: Текст.

        Returns:
            None

        Пример:
            >>> binding._report('поле обязательно')
        """
        if self._on_error is not None:
            self._on_error(message)
        else:
            self.widget.setToolTip(message)

    # ------------------------------------------------------------------ поле → виджет

    def _on_event(self, event: DataEvent) -> None:
        """
        Событие набора → обновить виджет (свои изменения поля — тоже: значение могли
        поправить другие виджеты того же поля).

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> binding._on_event(DataEvent(EventKind.REFRESHED, ds))
        """
        if event.kind in _REFRESH_EVENTS:
            self.refresh()
        elif event.kind is EventKind.ROW_CHANGED:
            ds = self.source.dataset
            if ds is not None and event.index == ds.current_index and (
                    not event.fields or self.field in event.fields or len(event.fields) > 1):
                self.refresh()

    def refresh(self) -> None:
        """
        Показывает значение поля текущей строки; включает/выключает правку.

        Returns:
            None

        Пример:
            >>> binding.refresh()
        """
        ds = self.source.dataset
        has_row = ds is not None and ds.active and ds.current_index >= 0
        value = ds.value(self.field) if has_row else None
        definition = ds.fields.get(self.field) if ds is not None else None
        if definition is not None and definition.local:
            editable = bool(has_row and definition.editable)       # отметка — и в «только чтение»
        else:
            editable = bool(has_row and ds.can_modify and (definition is None or definition.editable)
                            and (self.source.auto_edit or ds.state.editing))
        self._updating = True
        try:
            if isinstance(self.widget, QComboBox) and callable(self._choices):
                self._fill_choices()
            self._show(value, ds, has_row)
            self._set_editable(editable, has_row)
        finally:
            self._updating = False

    def _show(self, value: Any, ds: Optional[DataSet], has_row: bool) -> None:
        """
        Значение → виджет.

        Args:
            value: Значение.
            ds: Набор.
            has_row: Есть текущая строка.

        Returns:
            None

        Пример:
            >>> binding._show('Петров', ds, True)
        """
        w = self.widget
        text = ds.text(self.field) if has_row else ''
        if isinstance(w, QLineEdit):
            if w.text() != text:
                position = w.cursorPosition()
                w.setText(text)
                w.setCursorPosition(min(position, len(text)))
        elif isinstance(w, (QPlainTextEdit, QTextEdit)):
            if w.toPlainText() != text:
                w.setPlainText(text)
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setValue(value if isinstance(value, (int, float)) and not isinstance(value, bool)
                       else w.minimum())
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, QDateEdit):              # подкласс QDateTimeEdit — раньше него
            w.setSpecialValueText('—')
            w.setDate(QDate(value.year, value.month, value.day)
                      if isinstance(value, datetime.date) else w.minimumDate())
        elif isinstance(w, QDateTimeEdit):
            w.setSpecialValueText('—')
            if isinstance(value, datetime.datetime):
                w.setDateTime(QDateTime(QDate(value.year, value.month, value.day),
                                        QTime(value.hour, value.minute, value.second)))
            else:
                w.setDateTime(w.minimumDateTime())
        elif isinstance(w, QComboBox):
            index = w.findData(value)
            w.setCurrentIndex(index if index >= 0 else 0)
        elif isinstance(w, QLabel):
            if self._image:
                self._show_image(value)
            else:
                w.setText(text)

    def _show_image(self, value: Any) -> None:
        """
        Картинка в ``QLabel``: байты или путь к файлу; не картинка — пусто.

        Args:
            value: Байты или путь.

        Returns:
            None

        Пример:
            >>> binding._show_image('photos/1.jpg')
        """
        w = self.widget
        pixmap = QPixmap()
        if isinstance(value, (bytes, bytearray, memoryview)):
            pixmap.loadFromData(bytes(value))
        elif isinstance(value, str) and value:
            pixmap.load(value)
        if pixmap.isNull():
            w.clear()
            return
        size = w.size()
        if size.width() > 1 and size.height() > 1:
            pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        w.setPixmap(pixmap)

    def _set_editable(self, editable: bool, has_row: bool) -> None:
        """
        Правка в виджете: разрешена / только чтение / нет строки — выключен.

        Args:
            editable: Можно править.
            has_row: Есть текущая строка.

        Returns:
            None

        Пример:
            >>> binding._set_editable(True, True)
        """
        w = self.widget
        if isinstance(w, QLabel):
            return
        if isinstance(w, (QLineEdit, QPlainTextEdit, QTextEdit)):
            w.setReadOnly(not editable)
            w.setEnabled(has_row)
        elif isinstance(w, (QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit)):
            w.setReadOnly(not editable)
            w.setEnabled(has_row)
        else:
            w.setEnabled(editable)

    def unbind(self) -> None:
        """
        Разрывает связь (виджет перестаёт следить за набором и писать в него).

        Returns:
            None

        Пример:
            >>> binding.unbind()
        """
        self.source.unsubscribe(self._on_event)
        self._updating = True                              # сигналы виджета больше не пишут


def bind(widget: QWidget, source: DataSource, field: str, **options: Any) -> Binding:
    """
    Привязывает виджет к полю (см. ``Binding``).

    Args:
        widget: Виджет.
        source: Источник набора.
        field: Имя поля.
        **options: ``choices``, ``image``, ``on_error``.

    Returns:
        ``Binding``.

    Пример:
        >>> bind(QLineEdit(), source, 'last_name')
        <Binding QLineEdit→last_name>
    """
    return Binding(widget, source, field, **options)
