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
from typing import TYPE_CHECKING, Any, Dict, Hashable, Iterable, List, Optional, Sequence, Tuple, Union

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
        func: Вид итога (по умолчанию — число строк).
        field: Поле подчинённой строки для суммы/минимума/максимума/среднего.
        where: Дополнительные условия на подчинённые строки (только оплаченные чеки…).

    Пример:
        >>> AggregateDef(receipts, 'patient_id', AggFunc.SUM, 'amount').func.value
        'sum'
    """

    child: Union['DataSet', DataBackend]
    link_field: str
    func: AggFunc = AggFunc.COUNT
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
        object.__setattr__(self, 'func', AggFunc(self.func))
        object.__setattr__(self, 'where', tuple(self.where))
        if self.func is not AggFunc.COUNT and not self.field:
            raise ValueError(f"для итога {self.func.value!r} укажите поле (field)")

    @property
    def empty_value(self) -> Any:
        """
        Итог, когда подчинённых строк нет: 0 для числа, ``None`` для остальных.

        Returns:
            Значение.

        Пример:
            >>> AggregateDef(backend, 'a').empty_value
            0
        """
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

    def _rows(self, keys: Sequence[Hashable]) -> List[Dict[str, Any]]:
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
        for start in range(0, len(keys), CHUNK):
            part = list(keys[start:start + CHUNK])
            query = Query(conditions=(Condition(self.link_field, Op.IN, part),) + self.where)
            if backend.capabilities.filter:
                rows = [dict(r) for r in backend.fetch(query).rows]
            else:
                rows = [dict(r) for r in apply_in_memory(backend.fetch(Query()).rows, query, sort=False,
                                                         window=False)]
            if isinstance(writer, RowOverlay):
                rows = [dict(r) for r in writer.overlay(dataset, rows, query, True)]
                key_field = backend.key_field
                rows = [r for r in rows if writer.row_status(dataset, r.get(key_field)) != 'deleted']
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
        groups: Dict[Hashable, List[Any]] = {}
        for row in self._rows(real):
            parent = row.get(self.link_field)
            if parent in result:
                groups.setdefault(parent, []).append(row.get(self.field) if self.field else 1)
        for parent, values in groups.items():
            result[parent] = _apply(self.func, values)
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
