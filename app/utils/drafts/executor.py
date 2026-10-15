# app/utils/drafts/executor.py

"""
Исполнение плана сохранения в одной транзакции.

Хранилище данных (БД, API, файл) подключается адаптером — объектом с методами
``transaction``, ``create``, ``update``, ``delete`` (``PersistenceAdapter``). Пакет не
знает ни про SQLAlchemy, ни про сервисы приложения.

Порядок внутри транзакции: создание сверху вниз (в поле внешнего ключа подставляется
настоящий id только что созданного родителя), изменения, удаление снизу вверх.
Хранилище черновиков меняется ТОЛЬКО после успешной транзакции: при ошибке черновики
остаются как были (сохранение атомарно — D2 старой системы).

Пример:
    >>> plan = build_plan(store, None)
    >>> result = execute_plan(store, plan, SqlAlchemyAdapter(session_factory))
    >>> result.id_map
    {('appointment', -1): 55, ('photo', -2): 301}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Hashable, Mapping, Tuple

from ._model import NodeKey, PlanError, StalePlanError
from .plan import SavePlan

try:
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore

if TYPE_CHECKING:
    from .store import DraftStore


class PersistenceAdapter(Protocol):
    """
    Связь с хранилищем данных.

    ``transaction()`` — контекстный менеджер: при выходе без исключения фиксирует
    изменения, при исключении — откатывает (например, ``Session.begin()``). Объект,
    который он отдаёт (``tx``), передаётся в ``create``/``update``/``delete``.

    ``delete`` удаляет запись вместе с её потомками в хранилище данных (каскад БД или
    сам адаптер) — пакет черновиков знает только потомков, у которых есть черновики.

    Пример:
        >>> class MemoryAdapter:
        ...     def transaction(self): return contextlib.nullcontext(None)
        ...     def create(self, entity, data, tx): ...
        ...     def update(self, entity, entity_id, changes, tx): ...
        ...     def delete(self, entity, entity_id, tx): ...
    """

    def transaction(self) -> ContextManager[Any]:
        """
        Транзакция.

        Returns:
            Контекстный менеджер (отдаёт объект транзакции).

        Пример:
            >>> with adapter.transaction() as tx: ...
        """
        ...  # pragma: no cover

    def create(self, entity: str, data: Mapping[str, Any], tx: Any) -> Hashable:
        """
        Создаёт запись.

        Args:
            entity: Тип.
            data: Поля (внешний ключ на родителя уже настоящий).
            tx: Объект транзакции.

        Returns:
            Id созданной записи.

        Пример:
            >>> adapter.create('photo', {'appointment_id': 55, 'path': 'a.jpg'}, tx)
            301
        """
        ...  # pragma: no cover

    def update(self, entity: str, entity_id: Hashable, changes: Mapping[str, Any], tx: Any) -> None:
        """
        Изменяет поля записи.

        Args:
            entity: Тип.
            entity_id: Id.
            changes: Изменённые поля.
            tx: Объект транзакции.

        Returns:
            None

        Пример:
            >>> adapter.update('appointment', 12, {'cost': 500}, tx)
        """
        ...  # pragma: no cover

    def delete(self, entity: str, entity_id: Hashable, tx: Any) -> None:
        """
        Удаляет запись (с потомками в хранилище данных).

        Args:
            entity: Тип.
            entity_id: Id.
            tx: Объект транзакции.

        Returns:
            None

        Пример:
            >>> adapter.delete('appointment', 12, tx)
        """
        ...  # pragma: no cover


@dataclass(frozen=True)
class SaveResult:
    """
    Итог сохранения.

    Attributes:
        id_map: Временный ключ новой записи → id из хранилища данных.
        created: Созданные записи (ключи с НАСТОЯЩИМИ id).
        updated: Изменённые записи.
        deleted: Удалённые записи.
        dropped: Поглощённые черновики (внутри удалённых веток).

    Пример:
        >>> result.created
        (('appointment', 55), ('photo', 301))
    """

    id_map: Dict[NodeKey, Hashable] = field(default_factory=dict)
    created: Tuple[NodeKey, ...] = ()
    updated: Tuple[NodeKey, ...] = ()
    deleted: Tuple[NodeKey, ...] = ()
    dropped: Tuple[NodeKey, ...] = ()


def _real_id(store: 'DraftStore', entity: str, value: Any, id_map: Mapping[NodeKey, Hashable]) -> Any:
    """
    Значение внешнего ключа: временный id созданного в этой транзакции родителя →
    настоящий; иначе без изменений.

    Args:
        store: Хранилище (схема).
        entity: Тип записи, чей внешний ключ.
        value: Значение внешнего ключа.
        id_map: Карта созданных.

    Returns:
        Значение для хранилища данных.

    Пример:
        >>> _real_id(store, 'photo', -1, {('appointment', -1): 55})
        55
    """
    parent_type = store.schema.parent_type(entity)
    if parent_type is None:
        return value
    return id_map.get((parent_type, value), value)


def execute_plan(store: 'DraftStore', plan: SavePlan, adapter: PersistenceAdapter) -> SaveResult:
    """
    Выполняет план в одной транзакции; при успехе убирает сохранённые черновики и
    заменяет временные id настоящими (в том числе у оставшихся черновиков детей).

    Args:
        store: Хранилище черновиков (то же, по которому строился план).
        plan: План (``build_plan``).
        adapter: Связь с хранилищем данных.

    Returns:
        Итог сохранения.

    Raises:
        PlanError: В плане остались новые предки вне объёма (не спросили пользователя).
        StalePlanError: Черновики изменились после построения плана.
        Exception: Любая ошибка адаптера — транзакция откатывается, черновики не
            меняются, исключение пробрасывается.

    Пример:
        >>> execute_plan(store, build_plan(store, None), adapter).id_map
        {('photo', -1): 301}
    """
    if plan.missing_new_ancestors:
        raise PlanError(
            "сначала нужно решить с новыми родителями вне объёма: "
            + ", ".join(f"{t}:{i}" for t, i in plan.missing_new_ancestors)
        )
    if plan.store_token is not store.token:
        raise PlanError("план построен по другому хранилищу черновиков")
    if plan.version != store.version:
        raise StalePlanError("черновики изменились после построения плана — постройте план заново")
    if plan.is_empty:
        return SaveResult()

    id_map: Dict[NodeKey, Hashable] = {}
    with adapter.transaction() as tx:
        for draft in plan.creates:
            data = dict(draft.data)
            fk = store.schema.parent_field(draft.entity)
            if fk is not None:
                data[fk] = _real_id(store, draft.entity, draft.parent_id, id_map)
            new_id = adapter.create(draft.entity, data, tx)
            # F4 (проверка ядра 3): адаптер обязан вернуть id созданной записи; None
            # разнёс бы по детям ссылку на None. Исключение внутри транзакции — откат.
            if new_id is None:
                raise PlanError(f"адаптер не вернул id созданной записи {draft.entity}")
            id_map[draft.key] = new_id
        for draft in plan.updates:
            changes = dict(draft.data)
            fk = store.schema.parent_field(draft.entity)
            if fk is not None and fk in changes:
                changes[fk] = _real_id(store, draft.entity, changes[fk], id_map)
            adapter.update(draft.entity, draft.id, changes, tx)
        for draft in plan.deletes:
            adapter.delete(draft.entity, draft.id, tx)

    deleted = tuple(d.key for d in plan.deletes)
    # store._commit(plan.consumed, id_map, removed=deleted)
    # ↑ до 2026-10-16: закрытый метод хранилища; теперь открытый apply_saved
    store.apply_saved(plan.consumed, id_map, removed=deleted)
    return SaveResult(
        id_map=id_map,
        created=tuple((d.entity, id_map[d.key]) for d in plan.creates),
        updated=tuple(d.key for d in plan.updates),
        deleted=deleted,
        dropped=tuple(d.key for d in plan.dropped),
    )

