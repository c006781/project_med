# app/utils/dataset_qt/navigator.py

"""
Панель навигации по набору (аналог ``TDBNavigator`` RAD Studio).

Кнопки: первая, предыдущая, следующая, последняя, добавить, удалить, править,
сохранить, отменить, обновить. Доступность — по состоянию набора (правка идёт —
«сохранить»/«отменить»; набор нельзя менять — «добавить»/«удалить»/«править» выключены;
в начале/конце — стрелки). Ошибки — сигнал ``error_occurred`` (и, если включено, окно).

Дополнительные кнопки (например, отмена/повтор черновиков) — ``add_action``: панель не
знает, что они делают, — только когда они доступны (функция ``enabled``).

Зависит только от PySide6 и ядра ``dataset``.

Пример:
    >>> nav = DataNavigator(source)
    >>> nav.add_action('undo', '↶', 'Отменить действие', store.undo, enabled=store.can_undo)
    >>> layout.addWidget(nav)
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QToolButton, QWidget

try:  # пакеты лежат рядом в одном родительском пакете (как в этом проекте)
    from ..dataset import DataEvent, DataSource, State
except ImportError:  # pragma: no cover
    from dataset import DataEvent, DataSource, State

_log = logging.getLogger(__name__)

# Кнопка: (имя, значок, подсказка)
BUTTONS = (
    ('first', '⏮', 'Первая запись'),
    ('prior', '◀', 'Предыдущая запись'),
    ('next', '▶', 'Следующая запись'),
    ('last', '⏭', 'Последняя запись'),
    ('insert', '＋', 'Добавить запись'),
    ('delete', '−', 'Удалить запись'),
    ('edit', '✎', 'Править запись'),
    ('post', '✔', 'Сохранить правку'),
    ('cancel', '✖', 'Отменить правку'),
    ('refresh', '⟳', 'Обновить'),
)


class DataNavigator(QWidget):
    """
    Панель кнопок навигации и правки.

    Signals:
        error_occurred(str): Действие не удалось (текст для пользователя).

    Пример:
        >>> DataNavigator(source, buttons=['first', 'next', 'post']).buttons()
        ['first', 'next', 'post']
    """

    error_occurred = Signal(str)

    def __init__(self, source: DataSource, parent: Optional[QWidget] = None, *,
                 buttons: Optional[Sequence[str]] = None,
                 confirm_delete: Optional[Callable[[], bool]] = None,
                 show_errors: bool = True) -> None:
        """
        Args:
            source: Источник набора.
            parent: Родитель Qt.
            buttons: Какие кнопки показать (по умолчанию — все ``BUTTONS``).
            confirm_delete: Вопрос перед удалением (по умолчанию — окно «Удалить запись?»);
                ``lambda: True`` — без вопроса.
            show_errors: Показывать ошибки окном (сигнал — всегда).

        Пример:
            >>> DataNavigator(source, confirm_delete=lambda: True)
        """
        super().__init__(parent)
        self.source = source
        self._confirm_delete = confirm_delete or self._ask_delete
        self._show_errors = show_errors
        self._buttons: Dict[str, QToolButton] = {}
        self._extra: Dict[str, Callable[[], bool]] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        wanted = list(buttons) if buttons is not None else [b[0] for b in BUTTONS]
        for name, icon, tip in BUTTONS:
            if name in wanted:
                self._add_button(name, icon, tip, getattr(self, f'_do_{name}'))
        layout.addStretch(1)
        source.subscribe(self._on_event)
        self.update_buttons()

    def _add_button(self, name: str, icon: str, tip: str, handler: Callable[[], None]) -> QToolButton:
        """
        Добавляет кнопку.

        Args:
            name: Имя.
            icon: Значок (текст).
            tip: Подсказка.
            handler: Действие.

        Returns:
            Кнопка.

        Пример:
            >>> nav._add_button('x', 'X', 'Икс', print)
        """
        button = QToolButton(self)
        button.setText(icon)
        button.setToolTip(tip)
        button.setObjectName(f'nav_{name}')
        button.clicked.connect(lambda: self._run(handler))
        layout = self.layout()
        layout.insertWidget(len(self._buttons), button)
        self._buttons[name] = button
        return button

    def buttons(self):
        """
        Имена кнопок по порядку.

        Returns:
            Список имён.

        Пример:
            >>> nav.buttons()[:2]
            ['first', 'prior']
        """
        return list(self._buttons)

    def button(self, name: str) -> QToolButton:
        """
        Кнопка по имени.

        Args:
            name: Имя.

        Returns:
            ``QToolButton``.

        Пример:
            >>> nav.button('post').isEnabled()
            False
        """
        return self._buttons[name]

    def add_action(self, name: str, icon: str, tip: str, handler: Callable[[], object],
                   enabled: Optional[Callable[[], bool]] = None) -> QToolButton:
        """
        Своя кнопка (например, отмена/повтор черновиков).

        Args:
            name: Имя.
            icon: Значок.
            tip: Подсказка.
            handler: Действие (после него набор не перечитывается — это дело действия).
            enabled: Функция «доступна ли кнопка» (зовётся при каждом событии набора;
                именно функция — не готовое значение свойства).

        Returns:
            Кнопка.

        Пример:
            >>> nav.add_action('undo', '↶', 'Отменить', store.undo, enabled=store.can_undo)
        """
        button = self._add_button(name, icon, tip, lambda: handler())
        if enabled is not None:
            self._extra[name] = enabled
        self.update_buttons()
        return button

    # ------------------------------------------------------------------ действия

    def _run(self, action: Callable[[], object]) -> None:
        """
        Выполняет действие; ошибка — сигнал (и окно).

        Args:
            action: Действие.

        Returns:
            None

        Пример:
            >>> nav._run(ds.next)
        """
        try:
            action()
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            if self._show_errors:
                QMessageBox.warning(self, 'Ошибка', str(exc))
        self.update_buttons()

    def _ds(self):
        """
        Набор источника (нет — ошибка для пользователя).

        Returns:
            Набор.

        Raises:
            RuntimeError: Набора нет.

        Пример:
            >>> nav._ds()
            <DataSet patients browse rows=20>
        """
        ds = self.source.dataset
        if ds is None:
            raise RuntimeError('нет набора данных')
        return ds

    def _do_first(self) -> None:
        """Первая запись."""
        self._ds().first()

    def _do_prior(self) -> None:
        """Предыдущая запись."""
        self._ds().prior()

    def _do_next(self) -> None:
        """Следующая запись."""
        self._ds().next()

    def _do_last(self) -> None:
        """Последняя запись (порциями — догружает всё)."""
        self._ds().last()

    def _do_insert(self) -> None:
        """Новая запись в конце загруженных."""
        self._ds().append()

    def _do_delete(self) -> None:
        """Удаление текущей записи (с вопросом)."""
        ds = self._ds()
        if ds.state is State.INSERT or self._confirm_delete():
            ds.delete()

    def _do_edit(self) -> None:
        """Начать правку."""
        self._ds().edit()

    def _do_post(self) -> None:
        """Сохранить правку."""
        self._ds().post()

    def _do_cancel(self) -> None:
        """Отменить правку."""
        self._ds().cancel()

    def _do_refresh(self) -> None:
        """Перечитать набор."""
        self._ds().refresh()

    def _ask_delete(self) -> bool:
        """
        Вопрос «удалить?» окном.

        Returns:
            ``True`` — удалить.

        Пример:
            >>> nav._ask_delete()
            True
        """
        answer = QMessageBox.question(self, 'Удаление', 'Удалить запись?')
        return answer == QMessageBox.Yes

    # ------------------------------------------------------------------ доступность

    def _on_event(self, event: DataEvent) -> None:
        """
        Любое событие набора → пересчитать доступность кнопок.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> nav._on_event(event)
        """
        self.update_buttons()

    def update_buttons(self) -> None:
        """
        Доступность кнопок по состоянию набора.

        Returns:
            None

        Пример:
            >>> nav.update_buttons()
        """
        ds = self.source.dataset
        active = ds is not None and ds.active
        editing = active and ds.state.editing
        has_row = active and ds.current_index >= 0
        modify = active and ds.can_modify
        rules = {
            'first': active and not ds.bof,
            'prior': active and not ds.bof,
            'next': active and not ds.eof,
            'last': active and not ds.eof,
            'insert': modify,
            'delete': modify and has_row,
            'edit': modify and has_row and not editing,
            'post': editing,
            'cancel': editing,
            'refresh': active,
        }
        for name, button in self._buttons.items():
            if name in rules:
                button.setEnabled(bool(rules[name]))
            elif name in self._extra:
                try:
                    button.setEnabled(bool(self._extra[name]()))
                except Exception:
                    # ошибка в условии — кнопка выключена, причина — в журнал (иначе такую
                    # ошибку, например свойство вместо функции, не найти)
                    _log.exception("условие доступности кнопки %r упало", name)
                    button.setEnabled(False)

    def disconnect_source(self) -> None:
        """
        Отписывается от источника.

        Returns:
            None

        Пример:
            >>> nav.disconnect_source()
        """
        self.source.unsubscribe(self._on_event)
