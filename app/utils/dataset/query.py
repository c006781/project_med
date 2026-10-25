# app/utils/dataset/query.py

"""
Запрос к источнику: условия, сортировка, окно строк, параметры.

Запрос — данные, а не текст SQL: источник сам переводит его на язык своего хранилища
(SQL, REST, фильтр по списку). Чего источник не умеет, набор делает в памяти
(``apply_in_memory``) — так простой источник работает без лишнего кода.

Только стандартная библиотека.

Пример:
    >>> q = Query(conditions=(Condition('last_name', Op.STARTSWITH, 'Пет'),),
    ...           order=(Order('birth_date', descending=True),), limit=50)
    >>> rows = [{'last_name': 'Петров', 'birth_date': 2}, {'last_name': 'Иванов', 'birth_date': 1}]
    >>> apply_in_memory(rows, q)
    [{'last_name': 'Петров', 'birth_date': 2}]
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple


class Op(str, Enum):
    """
    Сравнение в условии.

    Пример:
        >>> Op.IN.value
        'in'
    """

    EQ = 'eq'
    NE = 'ne'
    LT = 'lt'
    LE = 'le'
    GT = 'gt'
    GE = 'ge'
    IN = 'in'
    CONTAINS = 'contains'         # подстрока, без учёта регистра
    STARTSWITH = 'startswith'     # начало строки, без учёта регистра
    IS_NULL = 'is_null'           # значение — True (пусто) / False (не пусто)


@dataclass(frozen=True)
class Condition:
    """
    Условие ``поле <сравнение> значение``. Условия запроса объединяются через «И».

    Attributes:
        field: Имя поля.
        op: Сравнение.
        value: Значение (для ``IN`` — набор значений, для ``IS_NULL`` — bool).

    Пример:
        >>> Condition('patient_id', Op.EQ, 5).matches({'patient_id': 5})
        True
    """

    field: str
    op: Op = Op.EQ
    value: Any = None

    def matches(
        self,
        row : Mapping[str, Any],  # проверяемая строка
    ) -> bool:
        """
        Подходит ли строка под условие (для источников без своей фильтрации).

        Сравнение с пустым значением (``None``) — всегда «не подходит» (как в SQL),
        кроме ``EQ None``/``NE None`` и ``IS_NULL``. В том числе ``IN``: пустое значение
        строки не подходит, даже если ``None`` есть в списке; пустой список (``None``) —
        ничего не подходит.

        Args:
            row: Строка.

        Returns:
            ``True`` — подходит.

        Пример:
            >>> Condition('name', Op.CONTAINS, 'ван').matches({'name': 'Иванов'})
            True
        """
        value = row.get(self.field)
        op = self.op
        if op is Op.IS_NULL:
            return (value is None) == bool(self.value)
        if op is Op.EQ:
            return value == self.value
        if op is Op.NE:
            return value != self.value
        if op is Op.IN:
            # return value in tuple(self.value)
            # ↑ до 2026-10-25 (DS1): пустое значение строки подходило, если None есть в
            # списке (в SQL и у источника поверх БД — нет), а пустой список ронял проверку
            return value is not None and value in tuple(self.value or ())
        if value is None or self.value is None:
            return False
        if op in (Op.CONTAINS, Op.STARTSWITH):
            text, part = str(value).casefold(), str(self.value).casefold()
            return part in text if op is Op.CONTAINS else text.startswith(part)
        try:
            if op is Op.LT:
                return value < self.value
            if op is Op.LE:
                return value <= self.value
            if op is Op.GT:
                return value > self.value
            if op is Op.GE:
                return value >= self.value
        except TypeError:            # несравнимые типы — не подходит, а не падение
            return False
        raise ValueError(f"неизвестное сравнение {op!r}")


@dataclass(frozen=True)
class Order:
    """
    Сортировка по полю.

    Attributes:
        field: Имя поля.
        descending: По убыванию.

    Пример:
        >>> Order.parse('-date')
        Order(field='date', descending=True)
    """

    field: str
    descending: bool = False

    @classmethod
    def parse(cls, text: str) -> 'Order':
        """
        Из записи ``'поле'`` / ``'-поле'`` (как ``order_by`` сервисов приложения).

        Args:
            text: Запись.

        Returns:
            ``Order``.

        Пример:
            >>> Order.parse('name')
            Order(field='name', descending=False)
        """
        return cls(text[1:], True) if text.startswith('-') else cls(text, False)


@dataclass(frozen=True)
class Query:
    """
    Запрос к источнику.

    Attributes:
        conditions: Условия (через «И»).
        order: Сортировка (по порядку важности).
        offset: Сколько строк пропустить.
        limit: Сколько строк вернуть (``None`` — все).
        params: Параметры для именованных запросов источника (что-то вроде
            ``{'search': 'Пет'}``) — смысл знает только источник.

    Пример:
        >>> Query(limit=10).window(20, 10)
        Query(conditions=(), order=(), offset=20, limit=10, params={})
    """

    conditions: Tuple[Condition, ...] = ()
    order: Tuple[Order, ...] = ()
    offset: int = 0
    limit: Optional[int] = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def window(self, offset: int, limit: Optional[int]) -> 'Query':
        """
        Тот же запрос для другого окна строк.

        Args:
            offset: Смещение.
            limit: Размер окна (``None`` — до конца).

        Returns:
            Новый ``Query``.

        Пример:
            >>> Query().window(0, 5).limit
            5
        """
        return replace(self, offset=offset, limit=limit)

    def where(self, *conditions: Condition) -> 'Query':
        """
        Тот же запрос с дополнительными условиями.

        Args:
            *conditions: Условия.

        Returns:
            Новый ``Query``.

        Пример:
            >>> len(Query().where(Condition('a', Op.EQ, 1)).conditions)
            1
        """
        return replace(self, conditions=self.conditions + tuple(conditions))


def _sort_key(value: Any) -> Tuple[int, Any]:
    """
    Ключ сортировки: пустые значения — в конце, разные типы не роняют сортировку.

    Args:
        value: Значение поля.

    Returns:
        Кортеж для сравнения.

    Пример:
        >>> sorted([None, 2, 1], key=_sort_key)
        [1, 2, None]
    """
    if value is None:
        return (2, '')
    if isinstance(value, str):
        return (1, value.casefold())
    return (0, value)


def sort_rows(rows: Iterable[Mapping[str, Any]], order: Sequence[Order]) -> List[Mapping[str, Any]]:
    """
    Сортирует строки в памяти (устойчиво: от младшего поля к старшему).

    Args:
        rows: Строки.
        order: Сортировка.

    Returns:
        Новый список.

    Пример:
        >>> sort_rows([{'a': 1}, {'a': 2}], [Order('a', True)])
        [{'a': 2}, {'a': 1}]
    """
    result = list(rows)
    for o in reversed(tuple(order)):
        try:
            result.sort(key=lambda r: _sort_key(r.get(o.field)), reverse=o.descending)
        except TypeError:          # несравнимые значения разных типов — по тексту
            result.sort(key=lambda r: str(r.get(o.field)), reverse=o.descending)
        # пустые — в конце и при сортировке по убыванию (устойчивая сортировка сохраняет
        # порядок остальных)
        result.sort(key=lambda r: r.get(o.field) is None)
    return result


def apply_in_memory(rows: Iterable[Mapping[str, Any]], query: Query, *, filter_: bool = True,
                    sort: bool = True, window: bool = True) -> List[Mapping[str, Any]]:
    """
    Выполняет запрос над списком строк: то, что источник не умеет сам.

    Args:
        rows: Строки.
        query: Запрос.
        filter_: Применять условия.
        sort: Применять сортировку.
        window: Применять окно (``offset``/``limit``).

    Returns:
        Подходящие строки.

    Пример:
        >>> apply_in_memory([{'a': 1}, {'a': 2}, {'a': 3}], Query(offset=1, limit=1))
        [{'a': 2}]
    """
    result = list(rows)
    if filter_ and query.conditions:
        result = [r for r in result if all(c.matches(r) for c in query.conditions)]
    if sort and query.order:
        result = sort_rows(result, query.order)
    if window:
        end = None if query.limit is None else query.offset + query.limit
        result = result[query.offset:end]
    return result
