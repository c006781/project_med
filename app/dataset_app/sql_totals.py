# app/dataset_app/sql_totals.py

"""
Итоги, которые считает БД, — ОТДЕЛЬНЫМ запросом (2026-10-18, мысль владельца).

Подсчёт (число фото у приёма, число приёмов у пациента) не встраивается в запрос самой
таблицы данных (как ``sql_compute``): тот запрос остаётся простым и не мешает вносить и
править данные. Отдельный объект делает свой запрос к подчинённой таблице:

    SELECT связь, COUNT(*), MAX(поле)… FROM подчинённая WHERE связь IN (:ключи окна) GROUP BY связь

и результат связывается со строками по ключу (``KeyedTotals`` ядра). Один запрос на окно —
сразу все столбцы объекта. Поправка на черновики — настраиваемая (``unsaved``): ``'delta'``
— к числу из БД прибавляются новые несохранённые подчинённые записи и вычитаются
помеченные на удаление и перенесённые.

Пример:
    >>> totals = SqlTotals(lambda: db.engine, Photo.__table__, 'appointment_id',
    ...                    {'photo_count': ('count', None), 'last_photo': ('max', 'id')})
    >>> totals.fetch([10, 11])
    {10: {'photo_count': 2, 'last_photo': 7}}
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Sequence, Tuple

import sqlalchemy as sa

from app.utils.dataset import DataSet, KeyedTotals

# Итог → функция SQL
_FUNCS = {'count': sa.func.count, 'sum': sa.func.sum, 'min': sa.func.min, 'max': sa.func.max,
          'avg': sa.func.avg}


class SqlTotals(KeyedTotals):
    """
    Итоги по подчинённой таблице одним SQL-запросом на окно строк.

    Пример:
        >>> SqlTotals(engine, Photo.__table__, 'appointment_id', {'n': ('count', None)}).columns
        {'n': ('count', None)}
    """

    def __init__(self, engine: Callable[[], Any], table: sa.Table, link_column: str,
                 columns: Mapping[str, Tuple[str, Optional[str]]], *,
                 where: Optional[Callable[[sa.Table], Any]] = None,
                 child: Optional[DataSet] = None, unsaved: str = 'delta') -> None:
        """
        Args:
            engine: Поставщик движка SQLAlchemy (берётся при каждом запросе — актуальная БД).
            table: Подчинённая таблица (``Photo.__table__``).
            link_column: Столбец связи с главной (``appointment_id``).
            columns: «столбец результата → (итог, поле)»: ``('count', None)``,
                ``('max', 'date')``…
            where: Своё условие на строки (``lambda t: t.c.paid.is_(True)``).
            child: Набор подчинённых (пересчёт на лету и поправка на черновики).
            unsaved: ``'delta'`` (по умолчанию; для чисел строк) или ``'ignore'``.

        Raises:
            ValueError: Неизвестный итог; поле не задано для не-числа.

        Пример:
            >>> SqlTotals(engine, table, 'x_id', {'s': ('median', 'a')})
            Traceback (most recent call last):
            ValueError: итог 'median': допустимо count, sum, min, max, avg
        """
        for name, (func, field_name) in columns.items():
            if func not in _FUNCS:
                raise ValueError(f"итог {func!r}: допустимо {', '.join(_FUNCS)}")
            if func != 'count' and not field_name:
                raise ValueError(f"итог {name} ({func}): укажите поле")
        counts = [name for name, (func, _) in columns.items() if func == 'count']
        use_delta = unsaved == 'delta' and child is not None and bool(counts)
        super().__init__(child=child, link_field=link_column,
                         unsaved='delta' if use_delta else 'ignore', counts=counts)
        self.engine = engine
        self.table = table
        self.link_column = link_column
        self.columns = dict(columns)
        self.where = where
        for name, (func, _) in self.columns.items():
            self._empty.setdefault(name, 0 if func == 'count' else None)

    def fetch(self, keys: Sequence[Hashable]) -> Dict[Hashable, Dict[str, Any]]:
        """
        Один запрос ``GROUP BY`` для ключей окна.

        Args:
            keys: Ключи главных строк (не более ``CHUNK`` за раз — режет ``compute_many``).

        Returns:
            «ключ → {столбец: значение}».

        Пример:
            >>> totals.fetch([10])
            {10: {'photo_count': 2}}
        """
        link = self.table.c[self.link_column]
        selected = [link]
        for name, (func, field_name) in self.columns.items():
            expression = _FUNCS[func]() if func == 'count' and not field_name else \
                _FUNCS[func](self.table.c[field_name])
            selected.append(expression.label(name))
        query = sa.select(*selected).where(link.in_(list(keys)))
        if self.where is not None:
            query = query.where(self.where(self.table))
        query = query.group_by(link)
        with self.engine().connect() as conn:
            rows = conn.execute(query).mappings().all()
        return {row[self.link_column]: {name: row[name] for name in self.columns} for row in rows}
