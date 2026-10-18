# app/utils/dataset/events.py

"""
События набора данных и подписка на них — без Qt.

Подписчик — функция от ``DataEvent``. Ошибка в одном подписчике не ломает набор и
других подписчиков: она пишется в журнал, рассылка продолжается.

Только стандартная библиотека.

Пример:
    >>> emitter = Emitter()
    >>> emitter.subscribe(lambda e: print(e.kind.value))
    >>> emitter.emit(DataEvent(EventKind.REFRESHED, dataset=None))
    refreshed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

if TYPE_CHECKING:
    from .dataset import DataSet

_log = logging.getLogger(__name__)


class EventKind(str, Enum):
    """
    Виды событий.

    * ``OPENED`` / ``CLOSED`` — набор открыт / закрыт;
    * ``REFRESHED`` — окно строк перечитано целиком (экран перерисовывает всё);
    * ``ROWS_INSERTED`` — строки добавлены (``index`` — первая, ``count`` — сколько):
      догрузка при прокрутке, новая строка;
    * ``ROWS_REMOVED`` — строки убраны (``index``, ``count``);
    * ``ROW_CHANGED`` — значения строки ``index`` изменились (``fields`` — какие);
    * ``CURRENT_CHANGED`` — сменилась текущая строка (``old``/``new`` — номера);
    * ``STATE_CHANGED`` — сменилось состояние (``old``/``new`` — ``State``);
    * ``ERROR`` — ошибка источника или записи (``error``).

    Пример:
        >>> EventKind('refreshed') is EventKind.REFRESHED
        True
    """

    OPENED = 'opened'
    CLOSED = 'closed'
    REFRESHED = 'refreshed'
    ROWS_INSERTED = 'rows_inserted'
    ROWS_REMOVED = 'rows_removed'
    ROW_CHANGED = 'row_changed'
    CURRENT_CHANGED = 'current_changed'
    STATE_CHANGED = 'state_changed'
    ERROR = 'error'


@dataclass(frozen=True)
class DataEvent:
    """
    Событие набора.

    Attributes:
        kind: Вид.
        dataset: Набор, в котором произошло.
        index: Номер строки (для событий о строках).
        count: Сколько строк (вставка/удаление).
        fields: Изменённые поля (``ROW_CHANGED``).
        old: Прежнее значение (номер строки, состояние).
        new: Новое значение.
        error: Исключение (``ERROR``).

    Пример:
        >>> DataEvent(EventKind.ROW_CHANGED, None, index=3, fields=('name',)).fields
        ('name',)
    """

    kind: EventKind
    dataset: Optional['DataSet']
    index: Optional[int] = None
    count: int = 0
    fields: Tuple[str, ...] = ()
    old: Any = None
    new: Any = None
    error: Optional[BaseException] = None


Listener = Callable[[DataEvent], None]


class Emitter:
    """
    Рассылка событий подписчикам.

    Подписчики вызываются в порядке подписки; подписка/отписка во время рассылки
    действует со следующего события.

    Пример:
        >>> e = Emitter(); seen = []
        >>> e.subscribe(seen.append); e.emit(DataEvent(EventKind.OPENED, None)); len(seen)
        1
    """

    def __init__(self) -> None:
        """
        Пустой список подписчиков.

        Пример:
            >>> Emitter().listeners
            ()
        """
        self._listeners: List[Listener] = []

    @property
    def listeners(self) -> Tuple[Listener, ...]:
        """
        Текущие подписчики.

        Returns:
            Кортеж функций.

        Пример:
            >>> Emitter().listeners
            ()
        """
        return tuple(self._listeners)

    def subscribe(self, listener: Listener) -> None:
        """
        Подписывает функцию (повторная подписка той же функции — без повтора).

        Args:
            listener: Функция от ``DataEvent``.

        Returns:
            None

        Пример:
            >>> e = Emitter(); e.subscribe(print); e.subscribe(print); len(e.listeners)
            1
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """
        Отписывает функцию (не подписана — ничего).

        Args:
            listener: Функция.

        Returns:
            None

        Пример:
            >>> Emitter().unsubscribe(print)
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def emit(self, event: DataEvent) -> None:
        """
        Рассылает событие. Ошибка подписчика — в журнал, рассылка продолжается.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> Emitter().emit(DataEvent(EventKind.CLOSED, None))
        """
        for listener in tuple(self._listeners):
            try:
                listener(event)
            except Exception:
                _log.exception("подписчик %r упал на событии %s", listener, event.kind.value)
