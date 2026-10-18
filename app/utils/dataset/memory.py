# app/utils/dataset/memory.py

"""
Источник строк в памяти — для тестов, примеров и проектов без хранилища.

Хранит копии строк (снаружи их не изменить); новый ключ — следующее целое число.

Только стандартная библиотека.

Пример:
    >>> backend = MemoryBackend([{'id': 1, 'name': 'А'}], fields=[FieldDef('id'), FieldDef('name')])
    >>> backend.insert({'name': 'Б'})
    {'name': 'Б', 'id': 2}
    >>> backend.fetch(Query(order=(Order('name', True),))).rows[0]['name']
    'Б'
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Hashable, Iterable, List, Mapping, Optional, Sequence

from .backend import Capabilities, Page
from .fields import FieldDef
from .query import Order, Query, apply_in_memory  # noqa: F401  (Order — для примеров)


class MemoryBackend:
    """
    Строки в памяти (``WritableBackend``).

    Attributes:
        key_field: Поле-ключ.
        capabilities: Умеет всё (фильтр/сортировка/окно/подсчёт — в памяти).

    Пример:
        >>> MemoryBackend([{'id': 5}]).get(5)
        {'id': 5}
    """

    capabilities = Capabilities()

    def __init__(self, rows: Iterable[Mapping[str, Any]] = (), *, key_field: str = 'id',
                 fields: Sequence[FieldDef] = ()) -> None:
        """
        Args:
            rows: Начальные строки (копируются).
            key_field: Поле-ключ.
            fields: Описание полей (пусто — набор возьмёт имена из строк).

        Raises:
            ValueError: У строки нет ключа или ключи повторяются.

        Пример:
            >>> MemoryBackend([{'id': 1}, {'id': 1}])
            Traceback (most recent call last):
            ValueError: ключ 1 повторяется
        """
        self.key_field = key_field
        self._fields = list(fields)
        self._rows: Dict[Hashable, Dict[str, Any]] = {}
        for row in rows:
            if key_field not in row:
                raise ValueError(f"у строки нет ключа {key_field!r}: {row!r}")
            key = row[key_field]
            if key in self._rows:
                raise ValueError(f"ключ {key!r} повторяется")
            self._rows[key] = copy.deepcopy(dict(row))
        self.fetch_count = 0          # сколько раз читали (для тестов догрузки)

    def fields(self) -> Sequence[FieldDef]:
        """
        Описание полей.

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> MemoryBackend([]).fields()
            []
        """
        return list(self._fields)

    def fetch(self, query: Query) -> Page:
        """
        Строки по запросу (копии).

        Args:
            query: Запрос.

        Returns:
            ``Page`` с общим числом подходящих строк.

        Пример:
            >>> MemoryBackend([{'id': 1}, {'id': 2}]).fetch(Query(limit=1))
            Page(rows=[{'id': 1}], total=2)
        """
        self.fetch_count += 1
        matched = apply_in_memory(self._rows.values(), query, window=False)
        end = None if query.limit is None else query.offset + query.limit
        return Page([copy.deepcopy(dict(r)) for r in matched[query.offset:end]], total=len(matched))

    def get(self, key: Hashable) -> Optional[Dict[str, Any]]:
        """
        Строка по ключу (копия).

        Args:
            key: Ключ.

        Returns:
            Строка или ``None``.

        Пример:
            >>> MemoryBackend([]).get(1) is None
            True
        """
        row = self._rows.get(key)
        return copy.deepcopy(row) if row is not None else None

    def _next_key(self) -> int:
        """
        Следующий целый ключ.

        Returns:
            Наибольший целый ключ + 1 (или 1).

        Пример:
            >>> MemoryBackend([{'id': 7}])._next_key()
            8
        """
        numbers = [k for k in self._rows if isinstance(k, int) and not isinstance(k, bool)]
        return max(numbers, default=0) + 1

    def insert(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Новая строка; ключ — заданный или следующий.

        Args:
            values: Значения.

        Returns:
            Строка (копия).

        Raises:
            ValueError: Ключ уже занят.

        Пример:
            >>> MemoryBackend([]).insert({'name': 'А'})
            {'name': 'А', 'id': 1}
        """
        row = copy.deepcopy(dict(values))
        if row.get(self.key_field) is None:
            row[self.key_field] = self._next_key()
        key = row[self.key_field]
        if key in self._rows:
            raise ValueError(f"ключ {key!r} уже занят")
        self._rows[key] = row
        return copy.deepcopy(row)

    def update(self, key: Hashable, changes: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Меняет строку (смена ключа не поддерживается).

        Args:
            key: Ключ.
            changes: Изменения.

        Returns:
            Строка после изменения (копия).

        Raises:
            KeyError: Нет строки.
            ValueError: Попытка сменить ключ.

        Пример:
            >>> MemoryBackend([{'id': 1, 'a': 1}]).update(1, {'a': 2})
            {'id': 1, 'a': 2}
        """
        if key not in self._rows:
            raise KeyError(f"нет строки с ключом {key!r}")
        if self.key_field in changes and changes[self.key_field] != key:
            raise ValueError("смена ключа записи не поддерживается")
        self._rows[key].update(copy.deepcopy(dict(changes)))
        return copy.deepcopy(self._rows[key])

    def delete(self, key: Hashable) -> None:
        """
        Удаляет строку.

        Args:
            key: Ключ.

        Returns:
            None

        Raises:
            KeyError: Нет строки.

        Пример:
            >>> MemoryBackend([{'id': 1}]).delete(1)
        """
        if key not in self._rows:
            raise KeyError(f"нет строки с ключом {key!r}")
        del self._rows[key]

    def all_rows(self) -> List[Dict[str, Any]]:
        """
        Все строки (копии) — для проверок в тестах.

        Returns:
            Список строк.

        Пример:
            >>> MemoryBackend([{'id': 1}]).all_rows()
            [{'id': 1}]
        """
        return [copy.deepcopy(r) for r in self._rows.values()]
