# app/utils/dataset/backend.py

"""
Протоколы: откуда набор берёт строки (``DataBackend``) и куда пишет изменения
(``DataWriter``).

Ядро не знает ни о каком хранилище (SQL, ORM, REST, файлы) и ни о каком механизме
отложенного сохранения (черновики): и то и другое подключается объектами, реализующими
эти протоколы.

* ``DataBackend`` — чтение: описание полей, строки по запросу, одна строка по ключу.
  ``capabilities`` говорит, что источник умеет сам (условия, сортировку, окно, подсчёт);
  остальное набор сделает в памяти.
* ``WritableBackend`` — источник, умеющий ещё и писать (``insert/update/delete``).
* ``DataWriter`` — способ записи для набора. По умолчанию — ``DirectWriter``: сразу в
  источник. Другой способ (например, копить правки в черновиках и сохранять разом) —
  свой объект с теми же тремя методами; ядро о нём ничего не знает.
* ``RowOverlay`` — необязательное дополнение к способу записи: показать поверх
  прочитанных строк ещё не сохранённое (изменённые значения, новые строки, пометки
  удаления) и сообщить состояние строки.

Только стандартная библиотека.

Пример:
    >>> from app.utils.dataset import DataSet, MemoryBackend
    >>> ds = DataSet(MemoryBackend([{'id': 1, 'name': 'А'}]))
    >>> isinstance(ds.writer, DirectWriter)
    True
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING, Any, Dict, Hashable, List, Mapping, Optional, Protocol, Sequence,
    runtime_checkable,
)

from .fields import FieldDef
from .query import Query

if TYPE_CHECKING:
    from .dataset import DataSet


@dataclass(frozen=True)
class Capabilities:
    """
    Что источник делает сам; остальное набор делает в памяти.

    Attributes:
        filter: Применяет условия запроса.
        sort: Применяет сортировку.
        window: Отдаёт окно строк (``offset``/``limit``).
        count: Сообщает общее число строк (``Page.total``).

    Если источник не умеет фильтровать или сортировать, он должен отдавать ВСЕ строки
    (окно тогда тоже делает набор) — иначе результат был бы неверным.

    Пример:
        >>> Capabilities(sort=False).sort
        False
    """

    filter: bool = True
    sort: bool = True
    window: bool = True
    count: bool = True


@dataclass(frozen=True)
class Page:
    """
    Ответ источника на запрос.

    Attributes:
        rows: Строки (словари «поле → значение»).
        total: Сколько всего строк под условиями (без окна); ``None`` — неизвестно.

    Пример:
        >>> Page([{'id': 1}], total=10).total
        10
    """

    rows: List[Dict[str, Any]] = field(default_factory=list)
    total: Optional[int] = None


@runtime_checkable
class DataBackend(Protocol):
    """
    Источник строк для набора (аналог связки ``TFDConnection`` + ``TFDTable``).

    Attributes:
        key_field: Имя поля-ключа записи.
        capabilities: Что источник умеет сам.

    Пример:
        >>> class Rest:
        ...     key_field = 'id'
        ...     capabilities = Capabilities(count=False)
        ...     def fields(self): return []
        ...     def fetch(self, query): return Page(requests.get(...).json())
        ...     def get(self, key): return requests.get(f'.../{key}').json()
    """

    key_field: str
    capabilities: Capabilities

    def fields(self) -> Sequence[FieldDef]:
        """
        Описание полей (пусто — набор возьмёт имена из первой строки или из своих полей).

        Returns:
            Последовательность ``FieldDef``.
        """

    def fetch(self, query: Query) -> Page:
        """
        Строки по запросу.

        Args:
            query: Запрос (условия, сортировка, окно, параметры).

        Returns:
            ``Page``.
        """

    def get(self, key: Hashable) -> Optional[Dict[str, Any]]:
        """
        Одна строка по ключу (обновление строки, подстановки).

        Args:
            key: Ключ.

        Returns:
            Строка или ``None`` — нет такой.
        """


@runtime_checkable
class WritableBackend(DataBackend, Protocol):
    """
    Источник, который умеет писать.

    Пример:
        >>> isinstance(MemoryBackend([]), WritableBackend)
        True
    """

    def insert(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Создаёт запись.

        Args:
            values: Значения хранимых полей.

        Returns:
            Строка, как она легла в хранилище (с ключом и значениями по умолчанию).
        """

    def update(self, key: Hashable, changes: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Меняет запись.

        Args:
            key: Ключ.
            changes: Изменённые поля.

        Returns:
            Строка после изменения.
        """

    def delete(self, key: Hashable) -> None:
        """
        Удаляет запись.

        Args:
            key: Ключ.
        """


@runtime_checkable
class DataWriter(Protocol):
    """
    Способ записи изменений набора. Набор зовёт его в ``post()`` и ``delete()``.

    Методы возвращают строку, которую набор покажет дальше (с ключом новой записи —
    настоящим или временным), — так способ записи может, например, отложить сохранение
    и выдать временный ключ.

    Пример:
        >>> class LogWriter:
        ...     def insert(self, ds, values): print('new', values); return dict(values, id=-1)
        ...     def update(self, ds, key, changes, row, original): print('upd', key, changes); return row
        ...     def delete(self, ds, key, row): print('del', key)
    """

    def insert(self, dataset: 'DataSet', values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Новая запись.

        Args:
            dataset: Набор, из которого пишут.
            values: Значения хранимых полей.

        Returns:
            Строка для показа (обязательно с ключом).
        """

    def update(self, dataset: 'DataSet', key: Hashable, changes: Mapping[str, Any],
               row: Mapping[str, Any], original: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Изменение записи.

        Args:
            dataset: Набор.
            key: Ключ.
            changes: Изменённые хранимые поля.
            row: Строка целиком после изменения (как её видит набор).
            original: Строка до правки (отложенная запись по ней узнаёт «вернули как было»).

        Returns:
            Строка для показа.
        """

    def delete(self, dataset: 'DataSet', key: Hashable, row: Mapping[str, Any]) -> None:
        """
        Удаление записи.

        Args:
            dataset: Набор.
            key: Ключ.
            row: Строка (последнее известное состояние).
        """


@runtime_checkable
class RowOverlay(Protocol):
    """
    Необязательное дополнение к способу записи: не сохранённое — поверх прочитанного.

    Набор зовёт ``overlay`` после каждого чтения строк из источника, ``row_status`` —
    когда экран спрашивает состояние строки (подсветка).

    Пример:
        >>> class Overlay:
        ...     def overlay(self, ds, rows, query, first): return rows
        ...     def row_status(self, ds, key): return None
    """

    def overlay(self, dataset: 'DataSet', rows: List[Dict[str, Any]], query: Query,
                first: bool) -> List[Dict[str, Any]]:
        """
        Строки окна с учётом не сохранённого.

        Args:
            dataset: Набор.
            rows: Прочитанные строки окна.
            query: Запрос, которым их прочли.
            first: Это первое окно (сюда добавляют новые, ещё не сохранённые строки,
                чтобы они не повторялись в каждом окне).

        Returns:
            Строки для показа (можно менять значения, убирать, добавлять).
        """

    def row_status(self, dataset: 'DataSet', key: Hashable) -> Optional[str]:
        """
        Состояние строки: ``'new'``, ``'modified'``, ``'deleted'`` или ``None`` — без изменений.

        Args:
            dataset: Набор.
            key: Ключ строки.

        Returns:
            Состояние.
        """


class ReadOnlyError(RuntimeError):
    """
    Запись невозможна: источник только для чтения и другого способа записи не задано.

    Пример:
        >>> raise ReadOnlyError('источник только для чтения')
        Traceback (most recent call last):
        ReadOnlyError: источник только для чтения
    """


class DirectWriter:
    """
    Способ записи по умолчанию: сразу в источник (``WritableBackend``).

    Пример:
        >>> ds = DataSet(MemoryBackend([]))            # writer = DirectWriter(backend)
        >>> ds.append({'name': 'А'}); ds.post()        # запись сразу в MemoryBackend
    """

    def __init__(self, backend: DataBackend) -> None:
        """
        Args:
            backend: Источник; если он не умеет писать — запись откажет ``ReadOnlyError``.

        Пример:
            >>> DirectWriter(MemoryBackend([])).writable
            True
        """
        self.backend = backend

    @property
    def writable(self) -> bool:
        """
        Умеет ли источник писать.

        Returns:
            ``True`` — умеет.

        Пример:
            >>> DirectWriter(MemoryBackend([])).writable
            True
        """
        return isinstance(self.backend, WritableBackend)

    def _require(self) -> WritableBackend:
        """
        Источник, умеющий писать.

        Returns:
            Источник.

        Raises:
            ReadOnlyError: Не умеет.

        Пример:
            >>> DirectWriter(MemoryBackend([]))._require()
            <...MemoryBackend ...>
        """
        if not self.writable:
            raise ReadOnlyError(f"источник {type(self.backend).__name__} только для чтения")
        return self.backend   # type: ignore[return-value]

    def insert(self, dataset: 'DataSet', values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Создаёт запись в источнике.

        Args:
            dataset: Набор.
            values: Значения.

        Returns:
            Строка из источника.

        Пример:
            >>> DirectWriter(MemoryBackend([])).insert(None, {'name': 'А'})
            {'name': 'А', 'id': 1}
        """
        return self._require().insert(values)

    def update(self, dataset: 'DataSet', key: Hashable, changes: Mapping[str, Any],
               row: Mapping[str, Any], original: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Меняет запись в источнике.

        Args:
            dataset: Набор.
            key: Ключ.
            changes: Изменённые поля.
            row: Строка целиком (не используется — источник вернёт свою).
            original: Строка до правки (не используется).

        Returns:
            Строка из источника.

        Пример:
            >>> DirectWriter(backend).update(None, 1, {'name': 'Б'}, {}, {})
            {'id': 1, 'name': 'Б'}
        """
        return self._require().update(key, changes)

    def delete(self, dataset: 'DataSet', key: Hashable, row: Mapping[str, Any]) -> None:
        """
        Удаляет запись в источнике.

        Args:
            dataset: Набор.
            key: Ключ.
            row: Строка (не используется).

        Returns:
            None

        Пример:
            >>> DirectWriter(backend).delete(None, 1, {})
        """
        self._require().delete(key)
