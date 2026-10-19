# app/schema/extras.py

"""
Свои столбцы и настройки связей в описании таблицы (без зависимостей от приложения — их
использует и описание таблиц ``app/schema``, и сборка наборов ``app/tables``).

* ``mark`` — отметка строки (галочка для массовых действий);
* ``calc`` — вычисляемый программой по своей строке;
* ``total`` — итог по подчинённой таблице (считает программа или БД отдельным запросом);
* ``ref`` — настройка связи-ссылки (правило удаления, переиспользуемые данные, показ).

Пример:
    >>> extras = (mark(), total('photo_count', 'Фото', 'photos', by='sql'))
    >>> links = (ref('doctor_id', 'doctors', on_delete='set_null'),)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Tuple

from app.utils.dataset import AggFunc, Condition, FieldKind


@dataclass(frozen=True)
class Extra:
    """
    Столбец, которого нет в ``field_configs``: отметка, вычисляемый по строке, итог по
    подчинённым (считает программа). Создаётся функциями ``mark``, ``calc``, ``total``.

    Attributes:
        name: Имя столбца.
        label: Подпись.
        kind: ``'mark'`` / ``'calc'`` / ``'total'``.
        value_kind: Тип значения (галочка, число…).
        func: Для ``calc`` — функция от строки (или от строки и сервиса таблицы).
        child: Для ``total`` — имя подчинённой таблицы реестра.
        aggregate: Для ``total`` — вид итога.
        field: Для ``total`` — поле подчинённой строки (сумма/мин/макс/среднее).
        where: Для ``total`` — условия на подчинённые строки.
        visible: Показывать столбцом по умолчанию.
        display: Показ значения текстом.
        widget: Виджет формы (``'image'`` — картинка…; см. ``dataset_qt.forms``).
        by: Для ``total`` — кто считает: ``'program'`` (по строкам, видит черновики) или
            ``'sql'`` (БД, отдельным запросом ``GROUP BY`` — не мешает правке таблицы данных).
        unsaved: Для ``total(by='sql')`` — поправка на черновики: ``'delta'`` (числа строк)
            или ``'ignore'``.
        sql_where: Для ``total(by='sql')`` — своё условие SQL на подчинённые строки.

    Пример:
        >>> mark('selected', '✓').kind
        'mark'
    """

    name: str
    label: str = ''
    kind: str = 'calc'
    value_kind: FieldKind = FieldKind.ANY
    func: Optional[Callable[..., Any]] = None
    child: Optional[str] = None
    aggregate: Any = AggFunc.COUNT
    field: Optional[str] = None
    where: Tuple[Condition, ...] = ()
    visible: bool = True
    display: Optional[Callable[[Any], str]] = None
    widget: Optional[str] = None
    by: str = 'program'
    unsaved: str = 'delta'
    sql_where: Optional[Callable[[Any], Any]] = None


def mark(name: str = 'mark', label: str = '✓') -> Extra:
    """
    Столбец-отметка (галочка): своё поле набора — в базу не пишется, переживает
    перечитывание, ставится без правки строки.

    Args:
        name: Имя.
        label: Подпись.

    Returns:
        ``Extra``.

    Пример:
        >>> mark().value_kind
        <FieldKind.BOOLEAN: 'boolean'>
    """
    return Extra(name, label, 'mark', FieldKind.BOOLEAN)


def calc(name: str, label: str, func: Callable[..., Any], kind: FieldKind = FieldKind.ANY, *,
         visible: bool = True, display: Optional[Callable[[Any], str]] = None,
         widget: Optional[str] = None) -> Extra:
    """
    Столбец, вычисляемый программой по своей строке.

    Args:
        name: Имя.
        label: Подпись.
        func: ``func(строка)`` или ``func(строка, сервис_таблицы)`` (второй аргумент —
            когда для вычисления нужен сервис: например, папка снимков).
        kind: Тип значения.
        visible: Показывать столбцом.
        display: Показ текстом.
        widget: Виджет формы (``'image'``…).

    Returns:
        ``Extra``.

    Пример:
        >>> calc('age', 'Возраст', lambda r: 2026 - r['birth_date'].year, FieldKind.INTEGER).kind
        'calc'
    """
    return Extra(name, label, 'calc', kind, func=func, visible=visible, display=display, widget=widget)


def total(name: str, label: str, child: str, func: Any = AggFunc.COUNT,
          field: Optional[str] = None, where: Sequence[Condition] = (), *,
          kind: Optional[FieldKind] = None, display: Optional[Callable[[Any], str]] = None,
          by: str = 'program', unsaved: str = 'delta',
          sql_where: Optional[Callable[[Any], Any]] = None) -> Extra:
    """
    Итог по подчинённой таблице реестра, который считает программа (число фото у приёма,
    сумма чеков у пациента).

    Args:
        name: Имя.
        label: Подпись.
        child: Подчинённая таблица (по имени в реестре).
        func: Вид итога (``AggFunc``) или своя функция от списка подчинённых строк —
            любая логика (``lambda rows: sum(r['amount'] for r in rows if r['paid'])``).
        field: Поле подчинённой строки (для суммы/мин/макс/среднего).
        where: Условия на подчинённые строки.
        kind: Тип значения (по умолчанию: число — целое, остальное — без проверки).
        display: Показ текстом.
        by: Кто считает: ``'program'`` (по строкам; видит черновики; любая своя функция)
            или ``'sql'`` (БД отдельным запросом; ``func`` — count/sum/min/max/avg).
        unsaved: Для ``by='sql'``: поправка на черновики — ``'delta'`` или ``'ignore'``.
        sql_where: Для ``by='sql'``: своё условие SQL (``lambda table: table.c.paid``).

    Returns:
        ``Extra``.

    Raises:
        ValueError: Неизвестный ``by``; для ``'sql'`` — своя функция или условия ``where``.

    Пример:
        >>> total('photo_count', 'Фото', 'photos').aggregate
        <AggFunc.COUNT: 'count'>
    """
    if not callable(func) or isinstance(func, AggFunc):
        func = AggFunc(func)
    if by not in ('program', 'sql'):
        raise ValueError(f"total {name}: by={by!r} — допустимо 'program' или 'sql'")
    if by == 'sql' and (not isinstance(func, AggFunc) or where):
        raise ValueError(f"total {name}: БД считает count/sum/min/max/avg; условия — sql_where")
    if kind is None:
        kind = FieldKind.INTEGER if func is AggFunc.COUNT else FieldKind.ANY
    return Extra(name, label, 'total', kind, child=child, aggregate=func, field=field,
                 where=tuple(where), display=display, by=by, unsaved=unsaved, sql_where=sql_where)


@dataclass(frozen=True)
class Link:
    """
    Связь-ссылка поля таблицы на другую таблицу реестра (не владение; 2026-10-18).

    Без описания каждый внешний ключ на таблицу реестра (кроме связи с родителем) —
    ссылка с правилом «нельзя удалить, пока ссылаются». Описание меняет правило.

    Attributes:
        field: Поле ссылки (``doctor_id``).
        table: Таблица цели (``doctors``).
        on_delete: Цель удаляют, а на неё ссылаются записи, которые не удаляются:
            ``'restrict'`` — отказ, ``'set_null'`` — ссылка обнуляется, ``'cascade'`` —
            ссылающиеся удаляются тоже.
        collect: Цель — переиспользуемые данные: удаляется, когда больше никому не нужна.
        display: Что показывать вместо id и в списке выбора: поле цели или функция от
            строки цели (по умолчанию — первое строковое видимое поле цели).

    Пример:
        >>> ref('doctor_id', 'doctors', on_delete='set_null').on_delete
        'set_null'
    """

    field: str
    table: str
    on_delete: str = 'restrict'
    collect: bool = False
    display: Any = None


def ref(field: str, table: str, on_delete: str = 'restrict', collect: bool = False,
        display: Any = None) -> Link:
    """
    Настройка связи-ссылки (см. ``Link``).

    Args:
        field: Поле ссылки.
        table: Таблица цели.
        on_delete: Правило удаления цели.
        collect: Цель — переиспользуемые данные.
        display: Показ цели (поле или функция от строки).

    Returns:
        ``Link``.

    Пример:
        >>> ref('template_id', 'templates', collect=True).collect
        True
    """
    return Link(field, table, on_delete, collect, display)
