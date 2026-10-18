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
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Hashable, List, Mapping, Tuple

from ._model import DeleteBlocked, NodeKey, PlanError, StalePlanError
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


def _map_references(store: 'DraftStore', entity: str, data: Dict[str, Any],
                    id_map: Mapping[NodeKey, Hashable]) -> None:
    """
    Ссылки на только что созданные записи — на их настоящие id (на месте).

    Args:
        store: Хранилище.
        entity: Тип записи.
        data: Поля для записи.
        id_map: «временный узел → настоящий id».

    Returns:
        None

    Пример:
        >>> _map_references(store, 'appointment', {'doctor_id': -3}, {('doctor', -3): 7})
    """
    for ref in store.schema.references(entity):
        value = data.get(ref.field)
        if value is not None and (ref.entity, value) in id_map:
            data[ref.field] = id_map[(ref.entity, value)]


def _human(store: 'DraftStore', node: NodeKey) -> str:
    """
    Запись для сообщения пользователю: «подпись типа #id» (подпись — из схемы).

    Args:
        store: Хранилище (схема).
        node: Узел.

    Returns:
        Текст.

    Пример:
        >>> _human(store, ('doctor', 5))
        '«Врач #5»'
    """
    entity_type = store.schema.get(node[0])
    return f"«{entity_type.label or node[0]} #{node[1]}»"


def _blocked_message(store: 'DraftStore', target: NodeKey, users: List[NodeKey], unsaved: bool) -> str:
    """
    Текст отказа в удалении: что удаляли и кто на это ссылается.

    Args:
        store: Хранилище.
        target: Удаляемая запись.
        users: Кто ссылается.
        unsaved: Ссылаются несохранённые изменения.

    Returns:
        Текст.

    Пример:
        >>> _blocked_message(store, ('doctor', 5), [('appointment', 12)], False)
        'Нельзя удалить «Врач #5»: на неё ссылаются: «Приём #12»'
    """
    shown = ', '.join(_human(store, n) for n in users[:10])
    more = f" и ещё {len(users) - 10}" if len(users) > 10 else ''
    who = "несохранённые изменения" if unsaved else "записи"
    return f"Нельзя удалить {_human(store, target)}: на неё ссылаются {who}: {shown}{more}"


def _check_unsaved_referrers(store: 'DraftStore', plan: SavePlan) -> None:
    """
    Удаляемую запись не должен использовать несохранённый черновик, который останется
    после сохранения (иначе потом он сохранился бы со ссылкой на удалённое).

    Args:
        store: Хранилище.
        plan: План.

    Returns:
        None

    Raises:
        DeleteBlocked: Есть такие черновики.

    Пример:
        >>> _check_unsaved_referrers(store, plan)
    """
    consumed = plan.consumed
    for draft in plan.deletes:
        users = []
        for referrer_type, ref in store.schema.referrers(draft.entity):
            for other in store.drafts(referrer_type):
                if other.key in consumed or other.deleted:
                    continue
                if other.data.get(ref.field) == draft.id:
                    users.append(other.key)
        if users:
            raise DeleteBlocked(draft.key, users, _blocked_message(store, draft.key, users, True))


def _delete_with_references(store: 'DraftStore', roots: List[NodeKey], adapter: Any, tx: Any) -> List[NodeKey]:
    """
    Удаление по правилам ссылок (внутри транзакции: правки уже записаны — БД отражает
    итог, на который и смотрят правила).

    Для каждой удаляемой записи: кто на неё ещё ссылается (кроме уже удаляемых) —
    ``restrict``: отказ (откат всего), ``set_null``: ссылка обнуляется, ``cascade``:
    ссылающиеся удаляются (раньше цели). После удаления — цели её ссылок с ``collect``,
    на которые больше никто не ссылается, удаляются тоже (рекурсивно).

    Нужен адаптер с ``referrers(тип, поле, ids, tx)`` (и ``read(тип, id, tx)`` для
    ``collect``), если у удаляемых типов есть ссылающиеся; иначе — как раньше.

    Args:
        store: Хранилище (схема).
        roots: Удаляемые узлы (из плана).
        adapter: Связь с БД.
        tx: Транзакция.

    Returns:
        Все удалённые узлы (в порядке удаления).

    Raises:
        DeleteBlocked: Удаление запрещено правилом ``restrict``.
        PlanError: Адаптер не умеет искать ссылки, а они описаны.

    Пример:
        >>> _delete_with_references(store, [('doctor', 5)], adapter, tx)
        [('doctor', 5)]
    """
    schema = store.schema
    needs = any(schema.referrers(entity) for entity, _ in roots) or any(
        ref.collect for entity, _ in roots for ref in schema.references(entity))
    if needs and not hasattr(adapter, 'referrers'):
        raise PlanError("в схеме описаны ссылки, а адаптер не умеет их искать (нет referrers) — "
                        "правила удаления проверить нельзя")
    removed: List[NodeKey] = []
    visiting: set = set()

    def users_of(node: NodeKey) -> List[Tuple[str, Any, List[Hashable]]]:
        """
        Кто ещё ссылается на запись (кроме удаляемых): ``(тип, ссылка, ids)``.

        Args:
            node: Узел.

        Returns:
            Список групп.

        Пример:
            >>> users_of(('doctor', 5))
            [('appointment', Reference(...), [12])]
        """
        groups = []
        for referrer_type, ref in schema.referrers(node[0]):
            ids = [i for i in adapter.referrers(referrer_type, ref.field, [node[1]], tx)
                   if (referrer_type, i) not in visiting]
            if ids:
                groups.append((referrer_type, ref, ids))
        return groups

    def remove(node: NodeKey) -> None:
        """
        Удаляет запись по правилам ссылок (рекурсивно).

        Args:
            node: Узел.

        Returns:
            None

        Пример:
            >>> remove(('doctor', 5))
        """
        if node in visiting:
            return
        visiting.add(node)
        collected = [ref for ref in schema.references(node[0]) if ref.collect]
        values = adapter.read(node[0], node[1], tx) if collected and hasattr(adapter, 'read') else None
        if hasattr(adapter, 'referrers'):
            for referrer_type, ref, ids in users_of(node):
                if ref.on_delete == 'restrict':
                    users = [(referrer_type, i) for i in ids]
                    raise DeleteBlocked(node, users, _blocked_message(store, node, users, False))
                if ref.on_delete == 'set_null':
                    for i in ids:
                        adapter.update(referrer_type, i, {ref.field: None}, tx)
                else:                                    # cascade
                    for i in ids:
                        remove((referrer_type, i))
        adapter.delete(node[0], node[1], tx)
        removed.append(node)
        for ref in collected:
            target = (values or {}).get(ref.field)
            if target is None or (ref.entity, target) in visiting:
                continue
            still_used = any(
                any((t, i) not in visiting for i in adapter.referrers(t, r.field, [target], tx))
                for t, r in schema.referrers(ref.entity))
            if not still_used:
                remove((ref.entity, target))

    for root in roots:
        remove(root)
    return removed


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

    _check_unsaved_referrers(store, plan)
    id_map: Dict[NodeKey, Hashable] = {}
    with adapter.transaction() as tx:
        for draft in plan.creates:
            data = dict(draft.data)
            fk = store.schema.parent_field(draft.entity)
            if fk is not None:
                data[fk] = _real_id(store, draft.entity, draft.parent_id, id_map)
            _map_references(store, draft.entity, data, id_map)
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
            _map_references(store, draft.entity, changes, id_map)
            adapter.update(draft.entity, draft.id, changes, tx)
        # for draft in plan.deletes:
        #     adapter.delete(draft.entity, draft.id, tx)
        # ↑ до 2026-10-18: удалялись только помеченные; теперь — по правилам ссылок
        #   (отказ / обнуление / каскад; ставшие ненужными переиспользуемые — тоже)
        removed = _delete_with_references(store, [d.key for d in plan.deletes], adapter, tx)

    # deleted = tuple(d.key for d in plan.deletes)
    deleted = tuple(removed)
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

