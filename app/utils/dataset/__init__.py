# app/utils/dataset/__init__.py

"""
Наборы данных в духе RAD Studio — переносимый пакет.

Только стандартная библиотека: ни Qt, ни БД, ни черновиков, ни кода приложения.
Хранилище подключается источником (``DataBackend``), способ записи — объектом
``DataWriter`` (по умолчанию — сразу в источник). Устройство — ``IMPLEMENTATION.md``.

Пример (главная → подчинённая):
    >>> from app.utils.dataset import (DataSet, DataSource, FieldDef, MasterDetailLink,
    ...                                MemoryBackend)
    >>> patients = DataSet(MemoryBackend([{'id': 1, 'name': 'Петров'}]), name='patients')
    >>> visits = DataSet(MemoryBackend([{'id': 10, 'patient_id': 1}],
    ...                                fields=[FieldDef('id'), FieldDef('patient_id', references='patients')]))
    >>> link = MasterDetailLink(DataSource(patients), visits)
    >>> patients.open(); visits.open(); visits.row_count
    1
"""

from .actions import Action, ActionSet, builtin_actions
from .aggregate import AggFunc, AggregateDef
from .backend import (
    Capabilities, DataBackend, DataWriter, DirectWriter, Page, ReadOnlyError, RowOverlay,
    WritableBackend,
)
from .dataset import DataSet, DataSetError, FetchMode, State, ValidationError
from .events import DataEvent, Emitter, EventKind, Listener
from .fields import FieldDef, FieldKind, Fields, Validator
from .links import LinkError, MasterDetailLink
from .lookup import LookupDef
from .memory import MemoryBackend
from .query import Condition, Op, Order, Query, apply_in_memory, sort_rows
from .source import DataSource

__all__ = [
    'Action', 'ActionSet', 'builtin_actions',
    'AggFunc', 'AggregateDef',
    'Capabilities', 'DataBackend', 'DataWriter', 'DirectWriter', 'Page', 'ReadOnlyError',
    'RowOverlay', 'WritableBackend',
    'DataSet', 'DataSetError', 'FetchMode', 'State', 'ValidationError',
    'DataEvent', 'Emitter', 'EventKind', 'Listener',
    'FieldDef', 'FieldKind', 'Fields', 'Validator',
    'LinkError', 'MasterDetailLink',
    'LookupDef',
    'MemoryBackend',
    'Condition', 'Op', 'Order', 'Query', 'apply_in_memory', 'sort_rows',
    'DataSource',
]
