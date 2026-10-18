# app/utils/dataset/dataset.py

"""
Набор данных — строки из источника, текущая строка, правка (аналог ``TDataSet`` RAD Studio).

Что делает:
    * **читает** строки источника по запросу (условия, сортировка, параметры) — всё сразу
      (``FetchMode.ALL``) или порциями при прокрутке (``FetchMode.ON_DEMAND``, размер
      порции — ``fetch_size``);
    * держит **текущую строку** и **состояние**: ``INACTIVE`` → ``BROWSE`` ⇄ ``EDIT`` /
      ``INSERT``; навигация ``first/prior/next/last/move_to/locate``;
    * **правка**: ``edit`` → ``set_value`` → ``post`` / ``cancel``; ``insert``/``append``;
      ``delete``. При ``post`` поля проверяются (``FieldDef.validate``), запись идёт через
      способ записи (``DataWriter``; по умолчанию — сразу в источник). Уход со строки во
      время правки сохраняет её (``auto_post``, как в RAD Studio) или отказывает;
    * **вычисляемые поля и подстановки** — при чтении значения (``value``);
    * **события** — подписка функцией (``subscribe``); экран слушает их через
      ``DataSource``.

Ключ записи, а не номер строки, — якорь текущей строки: после перечитывания курсор
возвращается на ту же запись, если она осталась.

Догрузка и сдвиги: если после чтения окна в хранилище появились/исчезли строки, смещение
следующей порции может «поехать». Набор не показывает строку дважды (повторы по ключу
отбрасываются), а удаление своей строки учитывает в смещении — пропусков из-за своих
удалений нет.

Только стандартная библиотека.

Пример:
    >>> ds = DataSet(MemoryBackend([{'id': 1, 'name': 'А'}, {'id': 2, 'name': 'Б'}]), fetch_size=1)
    >>> ds.open(); ds.row_count, ds.has_more
    (1, True)
    >>> ds.next(); ds.value('name')
    True
    'Б'
    >>> ds.edit(); ds.set_value('name', 'В'); ds.post(); ds.backend.get(2)['name']
    'В'
"""

from __future__ import annotations

import copy
import logging
from enum import Enum
from typing import (
    Any, Dict, Hashable, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union,
)

from .backend import DataBackend, DataWriter, DirectWriter, RowOverlay
from .events import DataEvent, Emitter, EventKind, Listener
from .fields import FieldDef, Fields
from .query import Condition, Order, Query, apply_in_memory

_log = logging.getLogger(__name__)


class State(str, Enum):
    """
    Состояние набора.

    Пример:
        >>> State.EDIT.editing, State.BROWSE.editing
        (True, False)
    """

    INACTIVE = 'inactive'
    BROWSE = 'browse'
    EDIT = 'edit'
    INSERT = 'insert'

    @property
    def editing(self) -> bool:
        """
        Идёт правка (``EDIT`` или ``INSERT``).

        Returns:
            ``True`` — правка.

        Пример:
            >>> State.INSERT.editing
            True
        """
        return self in (State.EDIT, State.INSERT)


class FetchMode(str, Enum):
    """
    Как загружать строки: ``ALL`` — все сразу; ``ON_DEMAND`` — порциями при прокрутке.

    Пример:
        >>> FetchMode('all') is FetchMode.ALL
        True
    """

    ALL = 'all'
    ON_DEMAND = 'on_demand'


class DataSetError(RuntimeError):
    """
    Действие невозможно в текущем состоянии набора.

    Пример:
        >>> raise DataSetError('набор не открыт')
        Traceback (most recent call last):
        DataSetError: набор не открыт
    """


class ValidationError(DataSetError):
    """
    Строка не прошла проверку полей при сохранении.

    Attributes:
        errors: «поле → список ошибок».

    Пример:
        >>> ValidationError({'name': ['поле «Имя» обязательно']}).errors['name']
        ['поле «Имя» обязательно']
    """

    def __init__(self, errors: Mapping[str, List[str]]) -> None:
        """
        Args:
            errors: Ошибки по полям.

        Пример:
            >>> str(ValidationError({'a': ['x']}))
            'x'
        """
        self.errors: Dict[str, List[str]] = {k: list(v) for k, v in errors.items()}
        super().__init__('; '.join(m for messages in self.errors.values() for m in messages))


OrderLike = Union[Order, str]


class DataSet:
    """
    Набор данных над источником.

    Attributes:
        backend: Источник строк.
        writer: Способ записи (``DirectWriter`` по умолчанию).
        name: Имя набора (обычно — имя таблицы): по нему связь «главная → подчинённая»
            находит поле-ссылку (``FieldDef.references``).
        fetch_mode: ``ALL`` / ``ON_DEMAND``.
        fetch_size: Строк в порции (``ON_DEMAND``) — и в первом окне.
        auto_post: Уход со строки во время правки сохраняет её (иначе — отказ).
        read_only: Правка запрещена.

    Пример:
        >>> ds = DataSet(MemoryBackend([]), name='patients', fetch_mode=FetchMode.ALL)
        >>> ds.state
        <State.INACTIVE: 'inactive'>
    """

    def __init__(
        self,
        backend: DataBackend,
        *,
        fields: Optional[Iterable[FieldDef]] = None,
        writer: Optional[DataWriter] = None,
        name: Optional[str] = None,
        fetch_mode: FetchMode = FetchMode.ON_DEMAND,
        fetch_size: int = 100,
        auto_post: bool = True,
        read_only: bool = False,
        order: Sequence[OrderLike] = (),
        conditions: Sequence[Condition] = (),
    ) -> None:
        """
        Args:
            backend: Источник строк.
            fields: Описание полей (по умолчанию — от источника; если и он молчит —
                имена из первой строки).
            writer: Способ записи (по умолчанию — ``DirectWriter(backend)``).
            name: Имя набора (для связей).
            fetch_mode: Всё сразу или порциями.
            fetch_size: Размер порции (> 0).
            auto_post: Сохранять правку при уходе со строки.
            read_only: Только чтение.
            order: Начальная сортировка (``Order`` или ``'-поле'``).
            conditions: Начальные условия.

        Raises:
            ValueError: ``fetch_size`` < 1.

        Пример:
            >>> DataSet(MemoryBackend([]), fetch_size=0)
            Traceback (most recent call last):
            ValueError: fetch_size должен быть > 0, получено 0
        """
        if fetch_size < 1:
            raise ValueError(f"fetch_size должен быть > 0, получено {fetch_size}")
        self.backend = backend
        self.writer: DataWriter = writer if writer is not None else DirectWriter(backend)
        self.name = name
        self.fetch_mode = FetchMode(fetch_mode)
        self.fetch_size = fetch_size
        self.auto_post = auto_post
        self.read_only = read_only
        self._given_fields = Fields(fields) if fields is not None else None
        self._fields: Fields = self._given_fields or Fields()
        self._order: Tuple[Order, ...] = tuple(_to_order(o) for o in order)
        self._conditions: Tuple[Condition, ...] = tuple(conditions)
        self._params: Dict[str, Any] = {}
        # связь «главная → подчинённая» (links.py): условия, значения для новых строк;
        # _master_blocked — главной строки нет: строк нет, добавлять нельзя
        self._master_conditions: Tuple[Condition, ...] = ()
        self._master_defaults: Dict[str, Any] = {}
        self._master_blocked = False
        self._state = State.INACTIVE
        self._rows: List[Dict[str, Any]] = []
        self._index = -1
        self._buffer: Optional[Dict[str, Any]] = None
        self._total: Optional[int] = None
        self._exhausted = True
        self._fetched = 0                    # строк получено из источника (смещение догрузки)
        self._fetched_keys: Set[Hashable] = set()
        self._emitter = Emitter()
        # описание полей — сразу (связи и экран настраиваются до открытия набора)
        self._resolve_fields(())

    # ------------------------------------------------------------------ свойства

    def __repr__(self) -> str:
        """
        Кратко: имя, состояние, строки.

        Returns:
            Строка.

        Пример:
            >>> DataSet(MemoryBackend([]), name='p')
            <DataSet p inactive rows=0>
        """
        return f"<DataSet {self.name or type(self.backend).__name__} {self._state.value} rows={len(self._rows)}>"

    @property
    def state(self) -> State:
        """
        Состояние.

        Returns:
            ``State``.

        Пример:
            >>> DataSet(MemoryBackend([])).state.value
            'inactive'
        """
        return self._state

    @property
    def active(self) -> bool:
        """
        Набор открыт.

        Returns:
            ``True`` — открыт.

        Пример:
            >>> DataSet(MemoryBackend([])).active
            False
        """
        return self._state is not State.INACTIVE

    @property
    def fields(self) -> Fields:
        """
        Описание полей.

        Returns:
            ``Fields``.

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 1, 'a': 2}])); ds.open(); ds.fields.names()
            ['id', 'a']
        """
        return self._fields

    @property
    def key_field(self) -> str:
        """
        Поле-ключ (от источника).

        Returns:
            Имя поля.

        Пример:
            >>> DataSet(MemoryBackend([])).key_field
            'id'
        """
        return self.backend.key_field

    @property
    def row_count(self) -> int:
        """
        Сколько строк загружено (с новыми, ещё не сохранёнными).

        Returns:
            Число строк.

        Пример:
            >>> DataSet(MemoryBackend([])).row_count
            0
        """
        return len(self._rows)

    @property
    def total(self) -> Optional[int]:
        """
        Сколько всего строк под условиями по словам источника (``None`` — неизвестно).

        Returns:
            Число или ``None``.

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 1}, {'id': 2}]), fetch_size=1); ds.open(); ds.total
            2
        """
        return self._total

    @property
    def has_more(self) -> bool:
        """
        Есть ли ещё не загруженные строки.

        Returns:
            ``True`` — можно догрузить.

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 1}]), fetch_size=1); ds.open(); ds.has_more
            False
        """
        return self.active and not self._exhausted

    @property
    def current_index(self) -> int:
        """
        Номер текущей строки (``-1`` — строк нет).

        Returns:
            Номер.

        Пример:
            >>> DataSet(MemoryBackend([])).current_index
            -1
        """
        return self._index

    @property
    def current_key(self) -> Optional[Hashable]:
        """
        Ключ текущей строки (``None`` — нет строки или новая без ключа).

        Returns:
            Ключ.

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 7}])); ds.open(); ds.current_key
            7
        """
        row = self._current_row()
        return None if row is None else row.get(self.key_field)

    @property
    def current(self) -> Optional[Dict[str, Any]]:
        """
        Текущая строка (копия; во время правки — с правками).

        Returns:
            Строка или ``None``.

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 7}])); ds.open(); ds.current
            {'id': 7}
        """
        row = self._current_row()
        return None if row is None else copy.deepcopy(row)

    @property
    def modified(self) -> bool:
        """
        Есть несохранённые правки текущей строки.

        Returns:
            ``True`` — есть.

        Пример:
            >>> DataSet(MemoryBackend([])).modified
            False
        """
        if self._state is State.INSERT:
            return True
        if self._state is State.EDIT and self._buffer is not None:
            return self._buffer != self._rows[self._index]
        return False

    @property
    def bof(self) -> bool:
        """
        На первой строке (или строк нет).

        Returns:
            ``True`` — в начале.

        Пример:
            >>> DataSet(MemoryBackend([])).bof
            True
        """
        return self._index <= 0

    @property
    def eof(self) -> bool:
        """
        На последней строке и больше не догрузить (или строк нет).

        Returns:
            ``True`` — в конце.

        Пример:
            >>> DataSet(MemoryBackend([])).eof
            True
        """
        return self._index >= len(self._rows) - 1 and not self.has_more

    @property
    def can_modify(self) -> bool:
        """
        Можно ли править: не только чтение, есть главная строка (для подчинённых),
        способ записи умеет писать.

        Returns:
            ``True`` — можно.

        Пример:
            >>> DataSet(MemoryBackend([]), read_only=True).can_modify
            False
        """
        if self.read_only or self._master_blocked:
            return False
        if isinstance(self.writer, DirectWriter):
            return self.writer.writable
        return True

    @property
    def query(self) -> Query:
        """
        Запрос, которым набор читает источник (условия связи + свои, сортировка, параметры).

        Returns:
            ``Query`` без окна.

        Пример:
            >>> DataSet(MemoryBackend([]), order=['-date']).query.order
            (Order(field='date', descending=True),)
        """
        return Query(conditions=self._master_conditions + self._conditions,
                     order=self._order, params=dict(self._params))

    # ------------------------------------------------------------------ события

    def subscribe(self, listener: Listener) -> None:
        """
        Подписка на события набора.

        Args:
            listener: Функция от ``DataEvent``.

        Returns:
            None

        Пример:
            >>> DataSet(MemoryBackend([])).subscribe(print)
        """
        self._emitter.subscribe(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """
        Отписка.

        Args:
            listener: Функция.

        Returns:
            None

        Пример:
            >>> DataSet(MemoryBackend([])).unsubscribe(print)
        """
        self._emitter.unsubscribe(listener)

    def _emit(self, kind: EventKind, **details: Any) -> None:
        """
        Рассылает событие набора.

        Args:
            kind: Вид.
            **details: Поля ``DataEvent``.

        Returns:
            None

        Пример:
            >>> ds._emit(EventKind.REFRESHED)
        """
        self._emitter.emit(DataEvent(kind, self, **details))

    def _set_state(self, state: State) -> None:
        """
        Меняет состояние с событием.

        Args:
            state: Новое состояние.

        Returns:
            None

        Пример:
            >>> ds._set_state(State.BROWSE)
        """
        if state is not self._state:
            old, self._state = self._state, state
            self._emit(EventKind.STATE_CHANGED, old=old, new=state)

    def _set_index(self, index: int) -> None:
        """
        Меняет текущую строку с событием.

        Args:
            index: Новый номер.

        Returns:
            None

        Пример:
            >>> ds._set_index(0)
        """
        if index != self._index:
            old, self._index = self._index, index
            self._emit(EventKind.CURRENT_CHANGED, old=old, new=index)

    def _force_index(self, index: int, old: Optional[int] = None) -> None:
        """
        Делает строку текущей и ВСЕГДА сообщает об этом — даже если номер тот же
        (под номером теперь другая запись: перечитали, вставили, удалили).

        D1 (2026-10-18): раньше номер сбрасывался в служебный -2, и событие приходило с
        «прежним номером» -2 — экран, перерисовывающий прежнюю строку, получал
        несуществующий номер.

        Args:
            index: Новый номер.
            old: Прежний номер (по умолчанию — текущий до вызова).

        Returns:
            None

        Пример:
            >>> ds._force_index(0)
        """
        old = self._index if old is None else old
        self._index = index
        self._emit(EventKind.CURRENT_CHANGED, old=old, new=index)

    # ------------------------------------------------------------------ чтение

    def _require_active(self) -> None:
        """
        Набор должен быть открыт.

        Returns:
            None

        Raises:
            DataSetError: Не открыт.

        Пример:
            >>> DataSet(MemoryBackend([]))._require_active()
            Traceback (most recent call last):
            DataSetError: набор не открыт
        """
        if not self.active:
            raise DataSetError("набор не открыт")

    def _resolve_fields(self, sample: Sequence[Mapping[str, Any]]) -> None:
        """
        Описание полей: заданное → от источника → имена из первой строки.

        Args:
            sample: Прочитанные строки.

        Returns:
            None

        Пример:
            >>> ds._resolve_fields([{'id': 1}])
        """
        if self._given_fields is not None:
            self._fields = self._given_fields
            return
        from_backend = list(self.backend.fields() or ())
        if from_backend:
            self._fields = Fields(from_backend)
        elif sample:
            self._fields = Fields.from_names(sample[0].keys())

    def _read(self, offset: int, limit: Optional[int]) -> Tuple[List[Dict[str, Any]], Optional[int], int]:
        """
        Читает окно строк: что источник не умеет, делается в памяти; затем — поверх
        не сохранённое (``RowOverlay`` способа записи).

        Args:
            offset: Смещение.
            limit: Размер окна (``None`` — все).

        Returns:
            ``(строки, всего, сколько получено от источника)``.

        Пример:
            >>> ds._read(0, 10)
            ([{'id': 1}], 1, 1)
        """
        query = self.query
        caps = self.backend.capabilities
        if caps.filter and caps.sort and caps.window:
            page = self.backend.fetch(query.window(offset, limit))
            rows, total = [dict(r) for r in page.rows], page.total if caps.count else None
        else:
            # источник отдаёт всё — остальное в памяти
            page = self.backend.fetch(query.window(0, None))
            matched = apply_in_memory(page.rows, query, filter_=not caps.filter,
                                      sort=not caps.sort, window=False)
            end = None if limit is None else offset + limit
            rows, total = [dict(r) for r in matched[offset:end]], len(matched)
        received = len(rows)
        if isinstance(self.writer, RowOverlay):
            rows = [dict(r) for r in self.writer.overlay(self, rows, query, offset == 0)]
        return rows, total, received

    def _load_first(self, at_least: int = 0) -> None:
        """
        Загружает первое окно заново (``ALL`` — всё).

        Args:
            at_least: Загрузить не меньше стольких строк (``refresh`` сохраняет
                прокрученное).

        Returns:
            None

        Пример:
            >>> ds._load_first()
        """
        self._rows, self._fetched, self._fetched_keys = [], 0, set()
        self._total, self._exhausted = None, True
        if self._master_blocked:
            return
        limit = None if self.fetch_mode is FetchMode.ALL else max(self.fetch_size, at_least)
        rows, total, received = self._read(0, limit)
        self._rows = rows
        self._fetched = received
        self._fetched_keys = {r.get(self.key_field) for r in rows}
        self._total = total
        self._exhausted = self._is_exhausted(limit, received)

    def _is_exhausted(self, limit: Optional[int], received: int) -> bool:
        """
        Всё ли прочитано из источника.

        Args:
            limit: Запрошенный размер окна.
            received: Сколько пришло.

        Returns:
            ``True`` — больше нечего догружать.

        Пример:
            >>> ds._is_exhausted(10, 3)
            True
        """
        if limit is None or received < limit:
            return True
        return self._total is not None and self._fetched >= self._total

    def open(self) -> None:
        """
        Открывает набор: читает первое окно, текущая — первая строка.

        Returns:
            None

        Raises:
            Exception: Ошибка источника (до неё набор остаётся закрытым; событие ``ERROR``).

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 1}])); ds.open(); ds.state.value
            'browse'
        """
        if self.active:
            return
        try:
            self._load_first()
        except Exception as exc:
            self._emit(EventKind.ERROR, error=exc)
            raise
        self._resolve_fields(self._rows)
        self._index = -1
        self._set_state(State.BROWSE)
        self._emit(EventKind.OPENED)
        self._emit(EventKind.REFRESHED)
        self._set_index(0 if self._rows else -1)

    def close(self) -> None:
        """
        Закрывает набор (несохранённая правка отбрасывается).

        Returns:
            None

        Пример:
            >>> ds.close(); ds.active
            False
        """
        if not self.active:
            return
        self._buffer = None
        self._rows, self._fetched, self._fetched_keys = [], 0, set()
        self._total, self._exhausted = None, True
        self._set_index(-1)
        self._set_state(State.INACTIVE)
        self._emit(EventKind.CLOSED)

    def refresh(self) -> None:
        """
        Перечитывает строки из источника; курсор — на ту же запись, если она осталась
        (иначе — на тот же номер, насколько возможно). Прокрученное (догруженное) не теряется.

        Returns:
            None

        Raises:
            DataSetError: Правка не сохранена и ``auto_post`` выключен.
            ValidationError: ``auto_post``, но строка не прошла проверку.

        Пример:
            >>> ds.refresh()
        """
        self._require_active()
        self.check_browse_mode()
        key, old_index, loaded = self.current_key, self._index, len(self._rows)
        try:
            self._load_first(at_least=loaded)
        except Exception as exc:
            self._emit(EventKind.ERROR, error=exc)
            raise
        self._emit(EventKind.REFRESHED)
        index = self._find(key) if key is not None else None
        if index is None:
            index = min(old_index, len(self._rows) - 1) if self._rows else -1
        self._force_index(index, old_index)

    def _find(self, key: Hashable) -> Optional[int]:
        """
        Номер загруженной строки по ключу.

        Args:
            key: Ключ.

        Returns:
            Номер или ``None``.

        Пример:
            >>> ds._find(7)
            0
        """
        for i, row in enumerate(self._rows):
            if row.get(self.key_field) == key:
                return i
        return None

    def fetch_more(self, count: Optional[int] = None) -> int:
        """
        Догружает следующую порцию (``ON_DEMAND``). Повторы по ключу отбрасываются.

        Args:
            count: Сколько строк (по умолчанию ``fetch_size``).

        Returns:
            Сколько строк добавилось.

        Пример:
            >>> ds = DataSet(MemoryBackend([{'id': 1}, {'id': 2}]), fetch_size=1); ds.open()
            >>> ds.fetch_more()
            1
        """
        if not self.has_more:
            return 0
        limit = count or self.fetch_size
        try:
            rows, total, received = self._read(self._fetched, limit)
        except Exception as exc:
            self._emit(EventKind.ERROR, error=exc)
            raise
        self._fetched += received
        self._total = total if total is not None else self._total
        self._exhausted = self._is_exhausted(limit, received)
        known = {r.get(self.key_field) for r in self._rows}
        fresh = [r for r in rows if r.get(self.key_field) not in known]
        if not fresh:
            return 0
        start = len(self._rows)
        self._rows.extend(fresh)
        self._fetched_keys.update(r.get(self.key_field) for r in fresh)
        self._emit(EventKind.ROWS_INSERTED, index=start, count=len(fresh))
        return len(fresh)

    def fetch_all(self) -> int:
        """
        Догружает всё оставшееся.

        Returns:
            Сколько строк добавилось.

        Пример:
            >>> ds.fetch_all()
            0
        """
        added = 0
        while self.has_more:
            before = self._fetched
            added += self.fetch_more()
            if self._fetched == before:      # источник больше ничего не отдаёт
                self._exhausted = True
        return added

    # ------------------------------------------------------------------ значения

    def _current_row(self) -> Optional[Dict[str, Any]]:
        """
        Текущая строка (во время правки — буфер правки), без копирования.

        Returns:
            Строка или ``None``.

        Пример:
            >>> ds._current_row()
            {'id': 1}
        """
        if self._state.editing and self._buffer is not None:
            return self._buffer
        if 0 <= self._index < len(self._rows):
            return self._rows[self._index]
        return None

    def _row_at(self, index: Optional[int]) -> Mapping[str, Any]:
        """
        Строка по номеру (``None`` — текущая; для текущей во время правки — буфер).

        Args:
            index: Номер или ``None``.

        Returns:
            Строка.

        Raises:
            IndexError: Нет такой строки.

        Пример:
            >>> ds._row_at(0)
            {'id': 1}
        """
        if index is None or (index == self._index and self._state.editing):
            row = self._current_row()
            if row is None:
                raise IndexError("нет текущей строки")
            return row
        if not 0 <= index < len(self._rows):
            raise IndexError(f"нет строки {index} (загружено {len(self._rows)})")
        return self._rows[index]

    def row(self, index: Optional[int] = None) -> Dict[str, Any]:
        """
        Хранимые значения строки (копия).

        Args:
            index: Номер (``None`` — текущая).

        Returns:
            Строка.

        Пример:
            >>> ds.row(0)
            {'id': 1}
        """
        return copy.deepcopy(dict(self._row_at(index)))

    def value(self, name: str, index: Optional[int] = None) -> Any:
        """
        Значение поля строки: хранимое, вычисляемое или подстановка.

        Поле без описания (источник вернул больше полей, чем описано) читается как есть.

        Args:
            name: Имя поля.
            index: Номер строки (``None`` — текущая; во время правки — с правками).

        Returns:
            Значение.

        Пример:
            >>> ds.value('name')
            'А'
        """
        row = self._row_at(index)
        definition = self._fields.get(name)
        if definition is not None:
            if definition.calculated is not None:
                return definition.calculated(row)
            if definition.lookup is not None:
                return definition.lookup.resolve(row.get(definition.lookup.key_field))
        return row.get(name)

    def text(self, name: str, index: Optional[int] = None) -> str:
        """
        Значение поля текстом (по ``FieldDef.text``).

        Args:
            name: Имя поля.
            index: Номер строки.

        Returns:
            Текст.

        Пример:
            >>> ds.text('id')
            '1'
        """
        value = self.value(name, index)
        definition = self._fields.get(name)
        if definition is None:
            return '' if value is None else str(value)
        return definition.text(value)

    def key_at(self, index: int) -> Optional[Hashable]:
        """
        Ключ строки по номеру.

        Args:
            index: Номер.

        Returns:
            Ключ.

        Пример:
            >>> ds.key_at(0)
            1
        """
        return self._row_at(index).get(self.key_field)

    def row_status(self, index: Optional[int] = None) -> Optional[str]:
        """
        Состояние строки для подсветки: ``'editing'``/``'inserting'`` (идёт правка),
        иначе — что скажет способ записи (``'new'``, ``'modified'``, ``'deleted'``) или ``None``.

        Args:
            index: Номер (``None`` — текущая).

        Returns:
            Состояние или ``None``.

        Пример:
            >>> ds.row_status(0) is None
            True
        """
        i = self._index if index is None else index
        if i == self._index and self._state is State.INSERT:
            return 'inserting'
        if i == self._index and self._state is State.EDIT:
            return 'editing'
        if isinstance(self.writer, RowOverlay) and 0 <= i < len(self._rows):
            return self.writer.row_status(self, self._rows[i].get(self.key_field))
        return None

    # ------------------------------------------------------------------ навигация

    def check_browse_mode(self) -> None:
        """
        Перед уходом со строки: правка сохраняется (``auto_post``) или отказ.

        Returns:
            None

        Raises:
            DataSetError: Правка не сохранена, ``auto_post`` выключен.
            ValidationError: Строка не прошла проверку.

        Пример:
            >>> ds.check_browse_mode()
        """
        if not self._state.editing:
            return
        if not self.auto_post:
            raise DataSetError("сначала сохраните или отмените правку")
        self.post()

    def move_to(self, index: int) -> None:
        """
        Делает текущей строку ``index`` (не загружена — догружает, ``ON_DEMAND``).

        Args:
            index: Номер.

        Returns:
            None

        Raises:
            IndexError: Нет такой строки.
            DataSetError / ValidationError: См. ``check_browse_mode``.

        Пример:
            >>> ds.move_to(0)
        """
        self._require_active()
        if index == self._index:
            return
        self.check_browse_mode()
        while index >= len(self._rows) and self.has_more:
            if not self.fetch_more():
                break
        if not 0 <= index < len(self._rows):
            raise IndexError(f"нет строки {index} (всего {len(self._rows)})")
        self._set_index(index)

    def first(self) -> bool:
        """
        На первую строку.

        Returns:
            ``True`` — строки есть.

        Пример:
            >>> ds.first()
            True
        """
        self._require_active()
        if not self._rows:
            return False
        self.move_to(0)
        return True

    def last(self) -> bool:
        """
        На последнюю строку (``ON_DEMAND`` — сначала догружает всё, как в RAD Studio).

        Returns:
            ``True`` — строки есть.

        Пример:
            >>> ds.last()
            True
        """
        self._require_active()
        self.check_browse_mode()
        self.fetch_all()
        if not self._rows:
            return False
        self.move_to(len(self._rows) - 1)
        return True

    def next(self) -> bool:
        """
        На следующую строку (на последней загруженной — догружает).

        Returns:
            ``True`` — перешли; ``False`` — дальше строк нет.

        Пример:
            >>> ds.next()
            False
        """
        self._require_active()
        if self._index + 1 >= len(self._rows):
            self.check_browse_mode()
            if not self.fetch_more():
                return False
        self.move_to(self._index + 1)
        return True

    def prior(self) -> bool:
        """
        На предыдущую строку.

        Returns:
            ``True`` — перешли; ``False`` — уже первая.

        Пример:
            >>> ds.prior()
            False
        """
        self._require_active()
        if self._index <= 0:
            return False
        self.move_to(self._index - 1)
        return True

    def locate(self, key: Hashable) -> bool:
        """
        Ищет запись по ключу (не загружена — догружает до неё) и делает текущей.

        Args:
            key: Ключ.

        Returns:
            ``True`` — найдена.

        Пример:
            >>> ds.locate(2)
            True
        """
        self._require_active()
        index = self._find(key)
        while index is None and self.has_more:
            before = len(self._rows)
            self.fetch_more()
            index = self._find(key)
            if len(self._rows) == before and index is None and not self.has_more:
                break
        if index is None:
            return False
        self.move_to(index)
        return True

    # ------------------------------------------------------------------ условия

    def set_filter(self, *conditions: Condition) -> None:
        """
        Заменяет свои условия (связь «главная → подчинённая» — отдельно) и перечитывает.

        Args:
            *conditions: Условия (пусто — без фильтра).

        Returns:
            None

        Пример:
            >>> ds.set_filter(Condition('name', Op.STARTSWITH, 'А'))
        """
        self.check_browse_mode()
        self._conditions = tuple(conditions)
        self._reload_if_active(keep_position=False)

    def set_order(self, *order: OrderLike) -> None:
        """
        Заменяет сортировку и перечитывает (курсор остаётся на той же записи).

        Args:
            *order: ``Order`` или ``'поле'``/``'-поле'``.

        Returns:
            None

        Пример:
            >>> ds.set_order('-date', 'id')
        """
        self.check_browse_mode()
        self._order = tuple(_to_order(o) for o in order)
        self._reload_if_active(keep_position=True)

    def set_params(self, **params: Any) -> None:
        """
        Параметры запроса для источника (именованные запросы) и перечитать.

        Args:
            **params: Параметры (значение ``None`` — убрать параметр).

        Returns:
            None

        Пример:
            >>> ds.set_params(search='Пет')
        """
        self.check_browse_mode()
        for name, value in params.items():
            if value is None:
                self._params.pop(name, None)
            else:
                self._params[name] = value
        self._reload_if_active(keep_position=False)

    def _reload_if_active(self, keep_position: bool) -> None:
        """
        Перечитывает открытый набор.

        Args:
            keep_position: Вернуть курсор на ту же запись (иначе — первая строка).

        Returns:
            None

        Пример:
            >>> ds._reload_if_active(False)
        """
        if not self.active:
            return
        if keep_position:
            self.refresh()
            return
        try:
            self._load_first()
        except Exception as exc:
            self._emit(EventKind.ERROR, error=exc)
            raise
        self._emit(EventKind.REFRESHED)
        self._force_index(0 if self._rows else -1)

    def set_master(self, values: Optional[Mapping[str, Any]]) -> None:
        """
        Условия связи с главной строкой (зовёт ``MasterDetailLink``).

        Args:
            values: «поле этого набора → значение главной строки»; ``None`` — главной
                строки нет (строк нет, добавлять нельзя).

        Returns:
            None

        Пример:
            >>> appointments.set_master({'patient_id': 5})
        """
        if self._state.editing:
            # правка подчинённой строки при смене главной — по правилу auto_post
            self.check_browse_mode()
        if values is None:
            changed = not self._master_blocked
            self._master_blocked = True
            self._master_conditions, self._master_defaults = (), {}
        else:
            conditions = tuple(Condition(f, value=v) for f, v in values.items())
            changed = self._master_blocked or conditions != self._master_conditions
            self._master_blocked = False
            self._master_conditions, self._master_defaults = conditions, dict(values)
        if changed:
            self._reload_if_active(keep_position=False)

    # ------------------------------------------------------------------ правка

    def _require_modifiable(self) -> None:
        """
        Правка разрешена.

        Returns:
            None

        Raises:
            DataSetError: Только чтение / нет главной строки / источник не пишет.

        Пример:
            >>> DataSet(MemoryBackend([]), read_only=True)._require_modifiable()
            Traceback (most recent call last):
            DataSetError: набор только для чтения
        """
        self._require_active()
        if self.read_only:
            raise DataSetError("набор только для чтения")
        if self._master_blocked:
            raise DataSetError("нет главной записи — сначала выберите или сохраните её")
        if not self.can_modify:
            raise DataSetError(f"источник {type(self.backend).__name__} только для чтения")

    def edit(self) -> None:
        """
        Начинает правку текущей строки (уже идёт — ничего).

        Returns:
            None

        Raises:
            DataSetError: Нет текущей строки / правка запрещена.

        Пример:
            >>> ds.edit(); ds.state.value
            'edit'
        """
        if self._state.editing:
            return
        self._require_modifiable()
        if self._current_row() is None:
            raise DataSetError("нет текущей строки")
        self._buffer = copy.deepcopy(self._rows[self._index])
        self._set_state(State.EDIT)

    def set_value(self, name: str, value: Any) -> None:
        """
        Меняет значение поля текущей строки (не в правке — начинает её, как AutoEdit).

        Args:
            name: Имя поля.
            value: Значение.

        Returns:
            None

        Raises:
            KeyError: Нет поля.
            DataSetError: Поле не редактируется / правка запрещена.

        Пример:
            >>> ds.set_value('name', 'Б')
        """
        definition = self._fields[name] if len(self._fields) else None
        if definition is not None and not definition.editable:
            raise DataSetError(f"поле «{definition.label}» только для чтения")
        if not self._state.editing:
            self.edit()
        assert self._buffer is not None
        if self._buffer.get(name, object()) == value and name in self._buffer:
            return
        self._buffer[name] = value
        self._emit(EventKind.ROW_CHANGED, index=self._index, fields=(name,))

    def _new_row(self, values: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        """
        Новая строка: значения по умолчанию полей + связь с главной + заданные.

        Args:
            values: Заданные значения.

        Returns:
            Строка.

        Пример:
            >>> ds._new_row({'name': 'А'})
            {'id': None, 'name': 'А'}
        """
        row: Dict[str, Any] = {f.name: f.default_value() for f in self._fields.stored()}
        row.setdefault(self.key_field, None)
        row.update(self._master_defaults)
        row.update(dict(values or {}))
        return row

    def _start_insert(self, at: int, values: Optional[Mapping[str, Any]]) -> None:
        """
        Начинает вставку строки в позицию ``at``.

        Args:
            at: Позиция.
            values: Начальные значения.

        Returns:
            None

        Пример:
            >>> ds._start_insert(0, None)
        """
        self.check_browse_mode()
        self._require_modifiable()
        row = self._new_row(values)
        self._rows.insert(at, row)
        self._buffer = copy.deepcopy(row)
        self._emit(EventKind.ROWS_INSERTED, index=at, count=1)
        self._force_index(at)
        self._set_state(State.INSERT)

    def insert(self, values: Optional[Mapping[str, Any]] = None) -> None:
        """
        Новая строка ПЕРЕД текущей (как ``Insert`` в RAD Studio).

        Args:
            values: Начальные значения.

        Returns:
            None

        Пример:
            >>> ds.insert({'name': 'А'}); ds.state.value
            'insert'
        """
        self._start_insert(max(self._index, 0), values)

    def append(self, values: Optional[Mapping[str, Any]] = None) -> None:
        """
        Новая строка в конце ЗАГРУЖЕННЫХ строк (без догрузки остального).

        Args:
            values: Начальные значения.

        Returns:
            None

        Пример:
            >>> ds.append({'name': 'Б'})
        """
        self._start_insert(len(self._rows), values)

    def _validate(self, row: Mapping[str, Any]) -> None:
        """
        Проверка всех описанных полей строки.

        Args:
            row: Строка.

        Returns:
            None

        Raises:
            ValidationError: Есть ошибки.

        Пример:
            >>> ds._validate({'name': ''})
            Traceback (most recent call last):
            ValidationError: поле «Имя» обязательно
        """
        errors: Dict[str, List[str]] = {}
        for definition in self._fields.stored():
            if definition.name == self.key_field and row.get(definition.name) is None:
                continue                  # ключ новой записи выдаст хранилище
            problems = definition.validate(row.get(definition.name), row)
            if problems:
                errors[definition.name] = problems
        if errors:
            raise ValidationError(errors)

    def _stored_values(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Только хранимые значения (без вычисляемых и подстановок; без пустого ключа).

        Args:
            row: Строка.

        Returns:
            Значения для записи.

        Пример:
            >>> ds._stored_values({'id': None, 'name': 'А'})
            {'name': 'А'}
        """
        computed = {f.name for f in self._fields if not f.stored}
        values = {k: v for k, v in row.items() if k not in computed}
        if values.get(self.key_field) is None:
            values.pop(self.key_field, None)
        return values

    def post(self) -> None:
        """
        Сохраняет правку текущей строки через способ записи.

        Ошибка проверки или записи — состояние правки сохраняется (можно исправить или
        отменить); ошибка записи — ещё и событие ``ERROR``.

        Returns:
            None

        Raises:
            ValidationError: Поля не прошли проверку.
            DataSetError: Способ записи не вернул ключ новой записи.
            Exception: Ошибка записи.

        Пример:
            >>> ds.set_value('name', 'Б'); ds.post(); ds.state.value
            'browse'
        """
        if not self._state.editing:
            return
        assert self._buffer is not None
        buffer = self._buffer
        self._validate(buffer)
        try:
            if self._state is State.INSERT:
                saved = self.writer.insert(self, self._stored_values(buffer))
                if saved is None or saved.get(self.key_field) is None:
                    raise DataSetError("способ записи не вернул ключ новой записи")
            else:
                original = self._rows[self._index]
                changes = {k: v for k, v in self._stored_values(buffer).items()
                           if original.get(k, object()) != v or k not in original}
                key = original.get(self.key_field)
                saved = self.writer.update(self, key, changes, buffer) if changes else buffer
        except Exception as exc:
            self._emit(EventKind.ERROR, error=exc)
            raise
        row = dict(buffer)
        row.update(dict(saved))
        self._rows[self._index] = row
        self._buffer = None
        self._set_state(State.BROWSE)
        self._emit(EventKind.ROW_CHANGED, index=self._index, fields=tuple(row))

    def cancel(self) -> None:
        """
        Отменяет правку: значения возвращаются, новая строка убирается.

        Returns:
            None

        Пример:
            >>> ds.cancel(); ds.state.value
            'browse'
        """
        if not self._state.editing:
            return
        state, self._buffer = self._state, None
        if state is State.INSERT:
            at = self._index
            del self._rows[at]
            self._set_state(State.BROWSE)
            self._emit(EventKind.ROWS_REMOVED, index=at, count=1)
            self._force_index(min(at, len(self._rows) - 1) if self._rows else -1, at)
        else:
            self._set_state(State.BROWSE)
            self._emit(EventKind.ROW_CHANGED, index=self._index, fields=tuple(self._rows[self._index]))

    def delete(self) -> None:
        """
        Удаляет текущую строку через способ записи (во время вставки — просто отмена;
        во время правки — правка отбрасывается).

        Если способ записи оставляет строку видимой с пометкой ``'deleted'``
        (``RowOverlay.row_status``), строка остаётся в наборе; иначе — убирается.

        Returns:
            None

        Raises:
            DataSetError: Нет строки / правка запрещена.
            Exception: Ошибка записи (событие ``ERROR``; строка остаётся).

        Пример:
            >>> ds.delete()
        """
        if self._state is State.INSERT:
            self.cancel()
            return
        self._require_modifiable()
        if self._state is State.EDIT:
            self.cancel()
        row = self._current_row()
        if row is None:
            raise DataSetError("нет текущей строки")
        key, at = row.get(self.key_field), self._index
        try:
            self.writer.delete(self, key, copy.deepcopy(row))
        except Exception as exc:
            self._emit(EventKind.ERROR, error=exc)
            raise
        if isinstance(self.writer, RowOverlay) and self.writer.row_status(self, key) == 'deleted':
            self._emit(EventKind.ROW_CHANGED, index=at, fields=())
            return
        del self._rows[at]
        if key in self._fetched_keys:
            self._fetched_keys.discard(key)
            self._fetched = max(self._fetched - 1, 0)   # следующая порция — без пропуска
        self._emit(EventKind.ROWS_REMOVED, index=at, count=1)
        self._force_index(min(at, len(self._rows) - 1) if self._rows else -1, at)

    def reload_row(self, index: Optional[int] = None) -> bool:
        """
        Перечитывает одну строку из источника (после изменения в другом месте).

        Args:
            index: Номер (``None`` — текущая).

        Returns:
            ``True`` — строка нашлась и обновлена; ``False`` — её больше нет (убрана).

        Пример:
            >>> ds.reload_row()
            True
        """
        self._require_active()
        i = self._index if index is None else index
        if i == self._index and self._state.editing:
            raise DataSetError("строка в правке — сначала сохраните или отмените")
        key = self.key_at(i)
        fresh = self.backend.get(key) if key is not None else None
        if fresh is not None and isinstance(self.writer, RowOverlay):
            overlaid = self.writer.overlay(self, [dict(fresh)], self.query, False)
            fresh = overlaid[0] if overlaid else None
        if fresh is None:
            del self._rows[i]
            self._emit(EventKind.ROWS_REMOVED, index=i, count=1)
            if i < self._index:
                self._force_index(self._index - 1)      # та же запись, номер на 1 меньше
            elif i == self._index:
                self._force_index(min(i, len(self._rows) - 1) if self._rows else -1, i)
            return False
        self._rows[i] = dict(fresh)
        self._emit(EventKind.ROW_CHANGED, index=i, fields=tuple(fresh))
        return True


def _to_order(item: OrderLike) -> Order:
    """
    ``Order`` из ``Order`` или записи ``'-поле'``.

    Args:
        item: Сортировка.

    Returns:
        ``Order``.

    Пример:
        >>> _to_order('-date')
        Order(field='date', descending=True)
    """
    return item if isinstance(item, Order) else Order.parse(item)
