# app/utils/drafts/__init__.py

"""
Черновики — несохранённые изменения записей, связанных деревом (переносимый пакет).

Только стандартная библиотека: ни Qt, ни БД, ни кода приложения. Подключение к
интерфейсу — подписка на события хранилища; к БД — адаптер ``PersistenceAdapter``.
Устройство — ``IMPLEMENTATION.md`` рядом.

Пример (вся цепочка):
    >>> from app.utils.drafts import (DraftStore, EntityType, SaveScope, TreeSchema,
    ...                               build_plan, execute_plan)
    >>> schema = TreeSchema([
    ...     EntityType('patient'),
    ...     EntityType('appointment', parent='patient', parent_field='patient_id'),
    ...     EntityType('photo', parent='appointment', parent_field='appointment_id'),
    ... ])
    >>> store = DraftStore(schema)
    >>> appointment = store.create('appointment', {'date': '2026-10-15'}, parent_id=1)
    >>> store.create('photo', {'path': 'a.jpg'}, parent_id=appointment)
    -2
    >>> plan = build_plan(store, [('appointment', appointment)], SaveScope.BRANCH)
    >>> execute_plan(store, plan, adapter).id_map
    {('appointment', -1): 55, ('photo', -2): 301}
"""

from ._model import (
    MISSING, Draft, DraftError, DraftEvent, NodeKey, PlanError, SchemaError, StalePlanError,
)
from .executor import PersistenceAdapter, SaveResult, execute_plan
from .plan import SavePlan, build_plan
from .policies import (
    CascadeDeletePolicy, DeletePolicy, DeleteResolution, RejectChildChangesPolicy,
)
from .schema import EntityType, TreeSchema
from .scope import SaveScope, select_nodes
from .store import DraftStore, negative_ids

__all__ = [
    'MISSING', 'Draft', 'DraftError', 'DraftEvent', 'NodeKey', 'PlanError', 'SchemaError',
    'StalePlanError',
    'PersistenceAdapter', 'SaveResult', 'execute_plan',
    'SavePlan', 'build_plan',
    'CascadeDeletePolicy', 'DeletePolicy', 'DeleteResolution', 'RejectChildChangesPolicy',
    'EntityType', 'TreeSchema',
    'SaveScope', 'select_nodes',
    'DraftStore', 'negative_ids',
]
