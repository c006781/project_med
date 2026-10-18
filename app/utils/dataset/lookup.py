# app/utils/dataset/lookup.py

"""
Подстановки — значение поля из другого источника по ключу (аналог lookup-полей RAD Studio).

Например, у приёма есть ``patient_id``, а показать нужно «Петров И. П.»: поле с
``lookup=LookupDef('patient_id', patients_backend, display='full_name')``. Результаты
запоминаются (кеш), чтобы таблица из сотни приёмов одного пациента не делала сотню
запросов. Источник — любой ``DataBackend`` или просто функция «ключ → строка».

Только стандартная библиотека.

Пример:
    >>> patients = MemoryBackend([{'id': 1, 'last_name': 'Петров'}])
    >>> who = LookupDef('patient_id', patients, display='last_name')
    >>> who.resolve(1), who.resolve(99)
    ('Петров', None)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Union

from .backend import DataBackend

RowGetter = Callable[[Hashable], Optional[Mapping[str, Any]]]
_MISSING = object()


@dataclass(frozen=True, eq=False)
class LookupDef:
    """
    Описание подстановки.

    Attributes:
        key_field: Поле строки, в котором лежит ключ (``patient_id``).
        source: Откуда брать: ``DataBackend`` (его ``get``) или функция «ключ → строка».
        display: Что показать: имя поля найденной строки или функция от строки.
        cache: Запоминать результаты (по умолчанию да; сбросить — ``invalidate``).

    Пример:
        >>> LookupDef('x', lambda key: {'name': f'#{key}'}, display='name').resolve(5)
        '#5'
    """

    key_field: str
    source: Union[DataBackend, RowGetter]
    display: Union[str, Callable[[Mapping[str, Any]], Any]]
    cache: bool = True
    _cache: Dict[Hashable, Any] = field(default_factory=dict, repr=False)

    def _row(self, key: Hashable) -> Optional[Mapping[str, Any]]:
        """
        Строка источника по ключу.

        Args:
            key: Ключ.

        Returns:
            Строка или ``None``.

        Пример:
            >>> LookupDef('x', lambda k: {'a': k}, 'a')._row(1)
            {'a': 1}
        """
        if hasattr(self.source, 'fetch') and hasattr(self.source, 'get'):
            return self.source.get(key)   # type: ignore[union-attr]  # источник (DataBackend)
        return self.source(key)           # type: ignore[operator]    # функция «ключ → строка»

    def resolve(self, key: Hashable) -> Any:
        """
        Значение для показа по ключу (``None`` для пустого ключа и ненайденной строки).

        Args:
            key: Ключ.

        Returns:
            Значение.

        Пример:
            >>> LookupDef('x', lambda k: None, 'a').resolve(1) is None
            True
        """
        if key is None:
            return None
        if self.cache:
            cached = self._cache.get(key, _MISSING)
            if cached is not _MISSING:
                return cached
        row = self._row(key)
        if row is None:
            value = None
        elif callable(self.display):
            value = self.display(row)
        else:
            value = row.get(self.display)
        if self.cache:
            self._cache[key] = value
        return value

    def invalidate(self, key: Optional[Hashable] = None) -> None:
        """
        Забывает запомненное (одну строку или всё) — после изменения источника.

        Args:
            key: Ключ; ``None`` — всё.

        Returns:
            None

        Пример:
            >>> who.invalidate()
        """
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)
