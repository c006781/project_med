# app/utils/dataset/aggregate.py

"""
Итоги по подчинённым строкам, которые считает программа (число фото у приёма, сумма
чеков у пациента, дата последнего приёма).

Второй способ — итог считает само хранилище (например, подзапросом SQL) и отдаёт его
полем строки: тогда это обычное поле ``persistent=False`` (сортировка и фильтр — в
хранилище по всей таблице, но не сохранённое оно не видит). Способ выбирается в
описании столбца.

Как считает программа:
    * **пачкой**: один запрос на окно строк — ``поле_связи IN (ключи окна)`` (ключи —
      кусками по ``CHUNK``: у хранилищ есть предел числа параметров), затем группировка;
    * **с несохранённым**: если подчинённый задан набором, поверх строк хранилища —
      способ записи этого набора (``RowOverlay``): новые строки считаются, помеченные на
      удаление — нет;
    * **на лету**: набор пересчитывает итог строки после изменений подчинённых
      (``DataSet.recalc``; связь «главная → подчинённая» и ``touch`` зовут его сами).

Только стандартная библиотека.

Пример:
    >>> photos = MemoryBackend([{'id': 1, 'appointment_id': 10}, {'id': 2, 'appointment_id': 10}])
    >>> count = AggregateDef(photos, 'appointment_id')
    >>> count.compute([10, 11])
    {10: 2, 11: 0}
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING, Any, Callable, Dict, Hashable, Iterable, List, Optional, Protocol, Sequence, Set,
    Tuple, Union, runtime_checkable,
)

from .backend import DataBackend, RowOverlay
from .query import Condition, Op, Query, apply_in_memory

if TYPE_CHECKING:
    from .dataset import DataSet

# Сколько ключей в одном запросе (у SQLite по умолчанию предел 999 параметров)
CHUNK = 500


class AggFunc(str, Enum):
    """
    Вид итога.

    Пример:
        >>> AggFunc.SUM.value
        'sum'
    """

    COUNT = 'count'
    SUM = 'sum'
    MIN = 'min'
    MAX = 'max'
    AVG = 'avg'


@dataclass(frozen=True, eq=False)
class AggregateDef:
    """
    Описание итога по подчинённым строкам.

    Attributes:
        child: Подчинённые строки: набор (``DataSet`` — учитывается и не сохранённое) или
            источник (``DataBackend`` — только то, что в хранилище).
        link_field: Поле подчинённой строки со ссылкой на главную (``appointment_id``).
        func: Вид итога (по умолчанию — число строк) или СВОЯ функция от списка
            подчинённых строк группы — любая логика (``lambda rows: …``; для главной строки
            без подчинённых зовётся с пустым списком).
        field: Поле подчинённой строки для суммы/минимума/максимума/среднего.
        where: Дополнительные условия на подчинённые строки (только оплаченные чеки…).

    Пример:
        >>> AggregateDef(receipts, 'patient_id', AggFunc.SUM, 'amount').func.value
        'sum'
    """

    child: Union['DataSet', DataBackend]
    link_field: str
    func: Union[AggFunc, Callable[[List[Dict[str, Any]]], Any]] = AggFunc.COUNT
    field: Optional[str] = None
    where: Tuple[Condition, ...] = ()

    def __post_init__(self) -> None:
        """
        Проверка: для суммы/минимума/максимума/среднего нужно поле.

        Returns:
            None

        Raises:
            ValueError: Нет поля для итога, которому оно нужно.

        Пример:
            >>> AggregateDef(backend, 'patient_id', AggFunc.SUM)
            Traceback (most recent call last):
            ValueError: для итога 'sum' укажите поле (field)
        """
        if not callable(self.func) or isinstance(self.func, AggFunc):
            object.__setattr__(self, 'func', AggFunc(self.func))
        object.__setattr__(self, 'where', tuple(self.where))
        if isinstance(self.func, AggFunc) and self.func is not AggFunc.COUNT and not self.field:
            raise ValueError(f"для итога {self.func.value!r} укажите поле (field)")

    @property
    def empty_value(self) -> Any:
        """
        Итог, когда подчинённых строк нет: 0 для числа, своя функция — от пустого списка,
        ``None`` для остальных.

        Returns:
            Значение.

        Пример:
            >>> AggregateDef(backend, 'a').empty_value
            0
        """
        if not isinstance(self.func, AggFunc):
            return self.func([])
        return 0 if self.func is AggFunc.COUNT else None

    def depends_on(self, dataset: 'DataSet') -> bool:
        """
        Зависит ли итог от этого набора (его строки — подчинённые итога).

        Args:
            dataset: Набор.

        Returns:
            ``True`` — да (подчинённым задан сам набор или его источник).

        Пример:
            >>> count.depends_on(photos_dataset)
            True
        """
        return self.child is dataset or self.child is getattr(dataset, 'backend', None)

    def _rows(
        self,
        keys : Sequence[Hashable],  # ключи главных строк
    ) -> List[Dict[str, Any]]:
        """
        Подчинённые строки для этих ключей главных строк (с не сохранённым, если
        подчинённый — набор с ``RowOverlay``; помеченные на удаление — без них).

        Args:
            keys: Ключи главных строк.

        Returns:
            Строки.

        Пример:
            >>> count._rows([10])
            [{'id': 1, 'appointment_id': 10}, {'id': 2, 'appointment_id': 10}]
        """
        dataset = self.child if hasattr(self.child, 'backend') and hasattr(self.child, 'writer') else None
        backend = dataset.backend if dataset is not None else self.child
        writer = dataset.writer if dataset is not None else None
        result: List[Dict[str, Any]] = []
        seen: Set[Hashable] = set()          # DS5: ключи подчинённых строк, уже взятых в итог
        for start in range(0, len(keys), CHUNK):
            part = list(keys[start:start + CHUNK])
            link = Condition(self.link_field, Op.IN, part)       # главные строки куска
            query = Query(
                conditions = (link,) + self.where,  # связь и условия итога
            )
            if backend.capabilities.filter:
                rows = [dict(r) for r in backend.fetch(query).rows]
            else:
                # источник не фильтрует — все строки, условия в памяти
                matched = apply_in_memory(
                    backend.fetch(Query()).rows,  # все строки источника
                    query,                        # связь и условия итога
                    sort   = False,               # порядок итогу не нужен
                    window = False,               # окна нет — все подходящие
                )
                rows = [dict(r) for r in matched]
            if isinstance(writer, RowOverlay):
                overlaid = writer.overlay(
                    dataset,  # подчинённый набор
                    rows,     # строки хранилища
                    query,    # запрос, которым их прочли
                    True,     # «первое окно» — с новыми несохранёнными строками
                )
                rows = [dict(r) for r in overlaid]
                key_field = backend.key_field
                rows = [r for r in rows if writer.row_status(dataset, r.get(key_field)) != 'deleted']
                # DS5 (2026-10-25): поверх хранилища — несохранённые значения, поэтому
                # условия итога (where) — заново: строка, переставшая им отвечать в
                # отложенной записи, раньше всё равно считалась. Новые строки способа
                # записи, не проверяющего условий запроса, приходят в каждом куске
                # ключей — берутся один раз (раньше — по разу на кусок). Условие связи
                # (IN ключей куска) заново не проверяется: строку, перенесённую к другой
                # главной, итог видит у новой (её отбирает compute)
                rows = [r for r in rows if all(c.matches(r) for c in self.where)]
                unique = []
                for row in rows:
                    key = row.get(key_field)
                    if key is None or key not in seen:
                        seen.add(key)
                        unique.append(row)
                rows = unique
            result.extend(rows)
        return result

    def compute(self, keys: Iterable[Hashable]) -> Dict[Hashable, Any]:
        """
        Итоги для ключей главных строк (пустой ключ — итог «нет строк»).

        Args:
            keys: Ключи главных строк.

        Returns:
            «ключ → итог».

        Пример:
            >>> AggregateDef(photos, 'appointment_id').compute([10])
            {10: 2}
        """
        wanted = list(dict.fromkeys(k for k in keys))
        result: Dict[Hashable, Any] = {k: self.empty_value for k in wanted}
        real = [k for k in wanted if k is not None]
        if not real:
            return result
        custom = not isinstance(self.func, AggFunc)
        groups: Dict[Hashable, List[Any]] = {}
        for row in self._rows(real):
            parent = row.get(self.link_field)
            if parent in result:
                # своя функция получает строки целиком; встроенные — значения поля
                item = row if custom else (row.get(self.field) if self.field else 1)
                groups.setdefault(parent, []).append(item)
        for parent, values in groups.items():
            result[parent] = self.func(values) if custom else _apply(self.func, values)
        return result


def _apply(func: AggFunc, values: List[Any]) -> Any:
    """
    Итог по значениям группы (пустые значения не участвуют в сумме/мин/макс/среднем).

    Args:
        func: Вид итога.
        values: Значения поля подчинённых строк (для числа — единицы).

    Returns:
        Итог.

    Пример:
        >>> _apply(AggFunc.SUM, [100, None, 50])
        150
    """
    if func is AggFunc.COUNT:
        return len(values)
    present = [v for v in values if v is not None]
    if not present:
        return None
    if func is AggFunc.SUM:
        return sum(present)
    if func is AggFunc.MIN:
        return min(present)
    if func is AggFunc.MAX:
        return max(present)
    return sum(present) / len(present)


# ----------------------------------------------------------------------------- объект-итоги по ключам

class KeyedTotals:
    """
    Отдельный объект «значения по ключам» для столбцов-итогов (2026-10-18, мысль владельца:
    считать в хранилище — например, SQL ``GROUP BY`` по подчинённой таблице, — но НЕ в запросе
    самой таблицы данных, чтобы не мешать вносить и править данные; результат связывается
    со строками по ключу).

    Один запрос на окно строк даёт сразу несколько столбцов (``column``); набор спрашивает
    объект ОДИН раз на окно, а не на каждый столбец.

    Наследник определяет ``fetch(keys)`` — как считать (SQL, REST, файл…). Поправка на не
    сохранённое (``unsaved='delta'``): к числу из хранилища прибавляются новые подчинённые
    строки и вычитаются удалённые/перенесённые — по способу записи подчинённого набора
    (``PendingChanges``); ``'ignore'`` — только хранилище.

    Пример:
        >>> class Counts(KeyedTotals):
        ...     def fetch(self, keys): return {k: {'n': 1} for k in keys}
        >>> counts = Counts(child=photos, link_field='appointment_id')
        >>> FieldDef('n', aggregate=counts.column('n', empty=0))
    """

    def __init__(self, *, child: Optional['DataSet'] = None, link_field: Optional[str] = None,
                 unsaved: str = 'ignore', counts: Sequence[str] = ()) -> None:
        """
        Args:
            child: Набор подчинённых строк (для пересчёта на лету и поправки на не сохранённое).
            link_field: Поле связи подчинённой строки с главной.
            unsaved: ``'delta'`` — поправка на не сохранённое (для столбцов-чисел ``counts``),
                ``'ignore'`` — только хранилище.
            counts: Какие столбцы — число строк (к ним применяется поправка).

        Raises:
            ValueError: Неизвестный режим или поправка без набора/поля связи.

        Пример:
            >>> KeyedTotals(unsaved='drop')
            Traceback (most recent call last):
            ValueError: unsaved: 'drop' — допустимо 'delta' или 'ignore'
        """
        if unsaved not in ('delta', 'ignore'):
            raise ValueError(f"unsaved: {unsaved!r} — допустимо 'delta' или 'ignore'")
        if unsaved == 'delta' and (child is None or not link_field):
            raise ValueError("поправке на не сохранённое нужны набор подчинённых (child) и поле связи")
        self.child = child
        self.link_field = link_field
        self.unsaved = unsaved
        self.counts = tuple(counts)
        self._empty: Dict[str, Any] = {}

    def fetch(self, keys: Sequence[Hashable]) -> Dict[Hashable, Dict[str, Any]]:
        """
        Значения столбцов по ключам главных строк (из хранилища). Определяет наследник.

        Args:
            keys: Ключи (без ``None``).

        Returns:
            «ключ → {столбец: значение}» (ключа нет — значения «пусто»).

        Raises:
            NotImplementedError: Не определено.

        Пример:
            >>> SqlTotals(...).fetch([10, 11])
            {10: {'photo_count': 2}}
        """
        raise NotImplementedError

    def column(self, name: str, empty: Any = None) -> 'TotalColumn':
        """
        Столбец этого объекта — для ``FieldDef(aggregate=...)``.

        Args:
            name: Имя столбца в результате ``fetch``.
            empty: Значение, когда строк нет (число — 0).

        Returns:
            ``TotalColumn``.

        Пример:
            >>> FieldDef('photo_count', aggregate=totals.column('photo_count', 0))
        """
        self._empty[name] = empty
        return TotalColumn(self, name, empty)

    def depends_on(self, dataset: 'DataSet') -> bool:
        """
        Зависят ли итоги от набора (его строки — подчинённые).

        Args:
            dataset: Набор.

        Returns:
            ``True`` — да.

        Пример:
            >>> totals.depends_on(photos)
            True
        """
        return dataset is self.child

    def compute_many(self, keys: Iterable[Hashable]) -> Dict[Hashable, Dict[str, Any]]:
        """
        Все столбцы для ключей: хранилище + (если включено) поправка на не сохранённое.

        Args:
            keys: Ключи главных строк.

        Returns:
            «ключ → {столбец: значение}» для каждого запрошенного ключа.

        Пример:
            >>> totals.compute_many([10, None])
            {10: {'photo_count': 3}, None: {'photo_count': 0}}
        """
        wanted = list(dict.fromkeys(keys))
        real = [k for k in wanted if k is not None]
        stored: Dict[Hashable, Dict[str, Any]] = {}
        for start in range(0, len(real), CHUNK):
            stored.update(self.fetch(real[start:start + CHUNK]))
        result = {k: {**self._empty, **stored.get(k, {})} for k in wanted}
        if self.unsaved == 'delta' and self.counts:
            for key, delta in self._count_delta(set(real)).items():
                for name in self.counts:
                    result[key][name] = (result[key].get(name) or 0) + delta
        return result

    def _count_delta(
        self,
        keys : Set[Hashable],  # ключи главных строк
    ) -> Dict[Hashable, int]:
        """
        Поправка числа строк на не сохранённое подчинённого набора (``PendingChanges``).

        Args:
            keys: Ключи главных строк.

        Returns:
            «ключ → +/- сколько строк».

        Пример:
            >>> totals._count_delta({10})
            {10: 1}
        """
        writer = getattr(self.child, 'writer', None)
        if not hasattr(writer, 'pending'):
            return {}
        delta: Dict[Hashable, int] = {}
        for before, after in writer.pending(self.child):
            old = (before or {}).get(self.link_field)
            new = (after or {}).get(self.link_field)
            if old == new:
                continue
            if old in keys:
                delta[old] = delta.get(old, 0) - 1
            if new in keys:
                delta[new] = delta.get(new, 0) + 1
        return delta


@dataclass(frozen=True, eq=False)
class TotalColumn:
    """
    Столбец объекта-итогов (``KeyedTotals``) — то, что кладётся в ``FieldDef.aggregate``.

    Набор считает все столбцы одного объекта одним вызовом ``source.compute_many``.

    Attributes:
        source: Объект-итоги.
        name: Имя столбца.
        empty: Значение, когда строк нет.

    Пример:
        >>> TotalColumn(totals, 'photo_count', 0).empty_value
        0
    """

    source: KeyedTotals
    name: str
    empty: Any = None

    @property
    def empty_value(self) -> Any:
        """
        Значение, когда подчинённых строк нет.

        Returns:
            Значение.

        Пример:
            >>> column.empty_value
            0
        """
        return self.empty

    def depends_on(self, dataset: 'DataSet') -> bool:
        """
        См. ``KeyedTotals.depends_on``.

        Args:
            dataset: Набор.

        Returns:
            ``True`` — зависит.

        Пример:
            >>> column.depends_on(photos)
            True
        """
        return self.source.depends_on(dataset)

    def compute(self, keys: Iterable[Hashable]) -> Dict[Hashable, Any]:
        """
        Только этот столбец (если спрашивают отдельно от остальных).

        Args:
            keys: Ключи.

        Returns:
            «ключ → значение».

        Пример:
            >>> column.compute([10])
            {10: 2}
        """
        return {k: v.get(self.name, self.empty) for k, v in self.source.compute_many(keys).items()}


@runtime_checkable
class PendingChanges(Protocol):
    """
    Необязательное умение способа записи: перечислить не сохранённые изменения строк набора
    (для поправки итогов, которые считает хранилище).

    Пример:
        >>> writer.pending(photos)
        [(None, {'id': -1, 'appointment_id': 10}), ({'id': 5, 'appointment_id': 10}, None)]
    """

    def pending(self, dataset: 'DataSet') -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
        """
        Не сохранённые изменения: ``(было, стало)`` — новая ``(None, строка)``, удалённая
        ``(строка, None)``, изменённая ``(до, после)`` (поле связи — обязательно, если менялось).

        Args:
            dataset: Набор.

        Returns:
            Список пар.

        Пример:
            >>> writer.pending(photos)
            [(None, {'id': -1, 'appointment_id': 10})]
        """
