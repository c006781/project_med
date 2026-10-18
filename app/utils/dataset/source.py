# app/utils/dataset/source.py

"""
Посредник между набором и экраном (аналог ``TDataSource`` RAD Studio).

Компоненты экрана подключаются к источнику, а не к набору:
    * набор можно **сменить на лету** (``source.dataset = другой``) — компоненты
      перерисуются по событию ``REFRESHED`` и не требуют переподключения;
    * извещения можно **приостановить** (``disable()`` / ``paused()``) — массовая правка
      без перерисовки на каждый шаг; при включении — одно ``REFRESHED``;
    * ``auto_edit`` — может ли компонент сам начать правку при вводе (как в RAD Studio).

Только стандартная библиотека.

Пример:
    >>> source = DataSource(ds)
    >>> source.subscribe(lambda e: print(e.kind.value))
    >>> with source.paused():
    ...     ds.refresh(); ds.refresh()        # подписчики молчат
    refreshed
"""

from __future__ import annotations

import contextlib
from typing import Iterator, Optional

from .dataset import DataSet
from .events import DataEvent, Emitter, EventKind, Listener


class DataSource:
    """
    Посредник: пересылает события набора подписчикам.

    Attributes:
        auto_edit: Компоненты могут сами начинать правку при вводе.

    Пример:
        >>> DataSource().dataset is None
        True
    """

    def __init__(self, dataset: Optional[DataSet] = None, *, enabled: bool = True,
                 auto_edit: bool = True) -> None:
        """
        Args:
            dataset: Набор (можно задать позже).
            enabled: Пересылать события сразу.
            auto_edit: Разрешить компонентам начинать правку.

        Пример:
            >>> DataSource(enabled=False).enabled
            False
        """
        self._dataset: Optional[DataSet] = None
        self._emitter = Emitter()
        self._enabled = enabled
        self._missed = False                 # были события, пока извещения выключены
        self.auto_edit = auto_edit
        self.dataset = dataset

    @property
    def dataset(self) -> Optional[DataSet]:
        """
        Подключённый набор.

        Returns:
            Набор или ``None``.

        Пример:
            >>> DataSource(ds).dataset is ds
            True
        """
        return self._dataset

    @dataset.setter
    def dataset(self, dataset: Optional[DataSet]) -> None:
        """
        Подключает другой набор; подписчики получают ``REFRESHED`` (или ``CLOSED``, если
        набора больше нет).

        Args:
            dataset: Новый набор или ``None``.

        Returns:
            None

        Пример:
            >>> source.dataset = other_ds
        """
        if dataset is self._dataset:
            return
        if self._dataset is not None:
            self._dataset.unsubscribe(self._forward)
        self._dataset = dataset
        if dataset is not None:
            dataset.subscribe(self._forward)
        self._notify(DataEvent(EventKind.REFRESHED if dataset is not None else EventKind.CLOSED,
                               dataset))

    @property
    def enabled(self) -> bool:
        """
        Пересылаются ли события.

        Returns:
            ``True`` — да.

        Пример:
            >>> DataSource().enabled
            True
        """
        return self._enabled

    def subscribe(self, listener: Listener) -> None:
        """
        Подписка компонента.

        Args:
            listener: Функция от ``DataEvent``.

        Returns:
            None

        Пример:
            >>> DataSource().subscribe(print)
        """
        self._emitter.subscribe(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """
        Отписка компонента.

        Args:
            listener: Функция.

        Returns:
            None

        Пример:
            >>> DataSource().unsubscribe(print)
        """
        self._emitter.unsubscribe(listener)

    def _forward(self, event: DataEvent) -> None:
        """
        Событие набора → подписчикам (или запомнить, что было, пока выключено).

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> source._forward(DataEvent(EventKind.REFRESHED, ds))
        """
        self._notify(event)

    def _notify(self, event: DataEvent) -> None:
        """
        Рассылает событие, если извещения включены.

        Ошибки (``ERROR``) рассылаются всегда — экран должен узнать о сбое и во время паузы.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> source._notify(DataEvent(EventKind.CLOSED, None))
        """
        if self._enabled or event.kind is EventKind.ERROR:
            self._emitter.emit(event)
        else:
            self._missed = True

    def disable(self) -> None:
        """
        Приостанавливает извещения (аналог ``DisableControls``).

        Returns:
            None

        Пример:
            >>> source.disable(); source.enabled
            False
        """
        self._enabled = False

    def enable(self) -> None:
        """
        Возобновляет извещения; если что-то пропущено — одно ``REFRESHED`` (экран
        перерисуется целиком и покажет текущую строку).

        Returns:
            None

        Пример:
            >>> source.enable()
        """
        if self._enabled:
            return
        self._enabled = True
        if self._missed:
            self._missed = False
            self._emitter.emit(DataEvent(EventKind.REFRESHED, self._dataset))

    @contextlib.contextmanager
    def paused(self) -> Iterator['DataSource']:
        """
        Пауза извещений на время блока (вложенные паузы — до внешнего конца).

        Returns:
            Контекст; внутри — сам источник.

        Пример:
            >>> with source.paused():
            ...     for _ in range(100): ds.append({'name': 'x'}); ds.post()
        """
        was_enabled = self._enabled
        self.disable()
        try:
            yield self
        finally:
            if was_enabled:
                self.enable()
