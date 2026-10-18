# app/tables/__init__.py

"""
Одно описание таблицы на всё приложение: из него — поля, свои столбцы (отметки,
вычисляемые, итоги по подчинённым), дерево таблиц, черновики, наборы данных, связи,
колонки и формы экрана. Устройство — ``IMPLEMENTATION.md`` рядом.

Пример:
    >>> from app.tables import CLINIC
    >>> built = CLINIC.build(); built.open()
    >>> built.appointments.value('photo_count')
    2
"""

from .clinic import CLINIC, photo_image, provider
from .spec import BuiltTables, Extra, Link, SpecError, TableRegistry, TableSpec, calc, mark, ref, total

__all__ = [
    'CLINIC', 'photo_image', 'provider',
    'BuiltTables', 'Extra', 'Link', 'SpecError', 'TableRegistry', 'TableSpec', 'calc', 'mark', 'ref', 'total',
]
