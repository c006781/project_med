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

from ._model import DeleteBlocked, Draft, NodeKey, PlanError, StalePlanError
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
        deleted: Удалённые записи (и помеченные, и перенесённые).
        dropped: Поглощённые черновики (внутри удалённых веток).
        moved_deleted: Из ``deleted`` — перенесённые в удалённую новую запись.

    Пример:
        >>> result.created
        (('appointment', 55), ('photo', 301))
    """

    id_map: Dict[NodeKey, Hashable] = field(default_factory=dict)
    created: Tuple[NodeKey, ...] = ()
    updated: Tuple[NodeKey, ...] = ()
    deleted: Tuple[NodeKey, ...] = ()
    dropped: Tuple[NodeKey, ...] = ()
    moved_deleted: Tuple[NodeKey, ...] = ()


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


def _check_unsaved_referrers(
    store : 'DraftStore',   # хранилище
    plan  : SavePlan,       # план
) -> None:
    """
    Проверяет, что удаляемую запись не использует несохранённый черновик, который останется
    после сохранения (иначе потом он сохранился бы со ссылкой на удалённое).

    Args:
        store : (DraftStore) Хранилище.
        plan  : (SavePlan) План.

    Raises:
        DeleteBlocked: Есть такие черновики.

    Example:
        >>> _check_unsaved_referrers(
        ...     store,  # хранилище
        ...     plan,   # план без таких черновиков
        ... )
    """
    consumed = plan.consumed
    # for draft in plan.deletes:
    # ↑ до 2026-11-07 (DR10): перенесённые записи (moved_deletes) удаляются так же
    for draft in (*plan.deletes, *plan.moved_deletes):
        users = []
        for referrer_type, ref in store.schema.referrers(draft.entity):
            for other in store.drafts(referrer_type):
                if other.key in consumed or other.deleted:
                    continue
                if other.data.get(ref.field) == draft.id:
                    users.append(other.key)
        if users:
            raise DeleteBlocked(draft.key, users, _blocked_message(store, draft.key, users, True))


# сверка перенесённых записей с БД перед удалением
def _moved_still_in_place(
    store   : 'DraftStore',       # хранилище (схема, подписи для сообщений)
    drafts  : Tuple[Draft, ...],  # перенесённые записи плана
    adapter : Any,                # связь с хранилищем данных
    tx      : Any,                # транзакция сохранения
) -> Tuple[List[NodeKey], List[NodeKey]]:
    """
    Проверяет внутри транзакции, что перенесённая запись лежит там, откуда её перенёс
    пользователь. Если родитель в БД другой, запись успели перенести мимо черновика
    (объединение, импорт, другое окно): такой перенос пользователь не делал и удалять запись
    нельзя — отказ и откат всего сохранения. Записи уже нет — удалять нечего.

    Args:
        store   : (DraftStore) Хранилище черновиков.
        drafts  : (Tuple[Draft, ...]) Перенесённые записи плана.
        adapter : (Any) Связь с хранилищем данных (нужен ``read``).
        tx      : (Any) Транзакция сохранения.

    Returns:
        (Tuple[List[NodeKey], List[NodeKey]]) ``(удалить, записей уже нет)``.

    Raises:
        PlanError: Адаптер не умеет читать записи (``нет read``) или родитель записи в БД
            другой (``Нельзя удалить «Фото #7»: её перенесли не через черновики …``).

    Example:
        >>> _moved_still_in_place(
        ...     store,                  # хранилище
        ...     plan.moved_deletes,     # фото 7, в БД всё ещё у прежнего приёма
        ...     adapter,                # связь с БД
        ...     tx,                     # транзакция
        ... )
        ([('photo', 7)], [])
    """
    if drafts and not hasattr(adapter, 'read'):
        raise PlanError("адаптер не умеет читать записи (нет read) — проверить, откуда "
                        "перенесена удаляемая запись, нельзя")
    present: List[NodeKey] = []
    gone: List[NodeKey] = []
    for draft in drafts:
        current = adapter.read(draft.entity, draft.id, tx)
        if current is None:
            gone.append(draft.key)
            continue
        fk = store.schema.parent_field(draft.entity)
        if current.get(fk) != draft.original[fk]:
            raise PlanError(
                f"Нельзя удалить {_human(store, draft.key)}: её перенесли не через черновики "
                f"(сейчас родитель #{current.get(fk)}, а пользователь переносил от "
                f"#{draft.original[fk]}). Отмените новую запись или перенос."
            )
        present.append(draft.key)
    return present, gone


def _delete_with_references(
    store   : 'DraftStore',     # хранилище (схема, подписи для сообщений)
    roots   : List[NodeKey],    # удаляемые узлы из плана (снизу вверх)
    adapter : Any,              # связь с хранилищем данных
    tx      : Any,              # транзакция сохранения
) -> List[NodeKey]: # удаление помеченных записей с запретом удалять используемое
    """
    Удаляет помеченные записи, проверяя ссылки на них (внутри транзакции: правки уже
    записаны — БД отражает итог, на который и смотрит проверка).

    Для каждой удаляемой записи: если на неё ещё ссылаются записи, которые не удалены
    раньше в этом же сохранении, — отказ ``DeleteBlocked`` (правило ``restrict``) и откат
    всего сохранения. Удаляются ТОЛЬКО помеченные записи: черновики данные БД сами не
    удаляют и не меняют сверх отданных изменений (2026-11-01) — ссылки не обнуляются,
    ссылающиеся записи и ставшие никому не нужными цели не удаляются (прежние
    ``set_null``, ``cascade``, ``collect`` убраны; описать их нельзя — ``SchemaError`` в
    ``Reference``).

    Цель ссылок, которую хранилище данных уже убрало в этой же транзакции (сервис удалил
    ставшую ненужной общую заметку, когда запись сменила текст), считается удалённой и
    повторно не удаляется (2026-10-31; проверяется, если адаптер умеет ``read``).

    Нужен адаптер с ``referrers(тип, поле, ids, tx)``, если на удаляемые типы описаны
    ссылки; иначе — как раньше (только ``delete``).

    Args:
        store   : (DraftStore) Хранилище черновиков (схема, подписи для сообщений).
        roots   : (List[NodeKey]) Удаляемые узлы из плана.
        adapter : (Any) Связь с хранилищем данных (``delete``; ``referrers``, ``read`` — при
            ссылках).
        tx      : (Any) Транзакция сохранения.

    Returns:
        (List[NodeKey]) Удалённые узлы в порядке удаления (те же, что ``roots``, без повторов).

    Raises:
        DeleteBlocked: На удаляемую запись ссылаются записи, которые не удаляются
            (``Нельзя удалить «Врач #5»: на неё ссылаются записи: «Приём #12»``).
        PlanError: Ссылки на удаляемые типы описаны, а адаптер не умеет их искать (нет
            ``referrers``).

    Example:
        >>> _delete_with_references(
        ...     store     =   store,            # схема со ссылкой приём → врач
        ...     roots     =   [('doctor', 5)],  # на врача никто не ссылается
        ...     adapter   =   adapter,          # связь с БД
        ...     tx        =   tx,               # транзакция сохранения
        ... )
        [('doctor', 5)]
    """
    schema = store.schema
    # needs = any(schema.referrers(entity) for entity, _ in roots) or any(
    #     ref.collect for entity, _ in roots for ref in schema.references(entity))
    # ↑ до 2026-11-01 (Ф1.6.3а): ссылки искались и ради collect (цели ссылок удаляемых
    #   записей); collect убран — нужны только ссылающиеся на удаляемые
    needs = any(schema.referrers(entity) for entity, _ in roots)
    if needs and not hasattr(adapter, 'referrers'):
        raise PlanError("в схеме описаны ссылки, а адаптер не умеет их искать (нет referrers) — "
                        "правила удаления проверить нельзя")
    removed: List[NodeKey] = []
    visiting: set = set()

    def users_of(
        node : NodeKey,     # удаляемый узел
    ) -> List[Tuple[str, Any, List[Hashable]]]: # кто ещё ссылается на запись
        """
        Находит записи, которые ссылаются на запись и ещё не удалены в этом сохранении.

        Args:
            node : (NodeKey) Удаляемый узел.

        Returns:
            (List[Tuple[str, Reference, List[Hashable]]]) Группы ``(тип, ссылка, ids)``;
                пусто — никто не ссылается.

        Example:
            >>> users_of(
            ...     ('doctor', 5),  # врач, на которого ссылается приём 12
            ... )
            [('appointment', Reference(...), [12])]
        """
        groups = []
        for referrer_type, ref in schema.referrers(node[0]):
            ids = [i for i in adapter.referrers(referrer_type, ref.field, [node[1]], tx)
                   if (referrer_type, i) not in visiting]
            if ids:
                groups.append((referrer_type, ref, ids))
        return groups

    def remove(
        node : NodeKey,     # удаляемый узел
    ) -> None: # удаление одной помеченной записи с проверкой ссылок
        """
        Удаляет одну помеченную запись; на неё ссылаются — отказ.

        Args:
            node : (NodeKey) Удаляемый узел.

        Raises:
            DeleteBlocked: На запись ссылаются записи, которые не удаляются.

        Example:
            >>> remove(
            ...     ('doctor', 5),  # на врача никто не ссылается
            ... )
        """
        if node in visiting:
            return
        visiting.add(node)
        # collected = [ref for ref in schema.references(node[0]) if ref.collect]
        # # values = adapter.read(node[0], node[1], tx) if collected and hasattr(adapter, 'read') else None
        # # ↑ до 2026-10-25 (DR7): без read у адаптера «переиспользуемые данные» молча не
        # #   удалялись (оставались никому не нужными) — теперь отказ, как и без referrers;
        # #   проверка здесь, а не до транзакции, — так она видит и записи, удаляемые каскадом.
        # if collected and not hasattr(adapter, 'read'):
        #     raise PlanError(
        #         f"у типа {node[0]} описаны переиспользуемые данные (collect), а адаптер не "
        #         "умеет читать запись (нет read) — что удалять следом, узнать нельзя"
        #     )
        # values = adapter.read(node[0], node[1], tx) if collected else None
        # ↑ до 2026-11-01 (Ф1.6.3а): для collect читались значения ссылок удаляемой записи
        #   (что удалять следом) и без read был отказ (DR7); черновики сами из БД ничего не
        #   убирают — чтение и эта проверка не нужны
        if hasattr(adapter, 'referrers'):
            # for referrer_type, ref, ids in users_of(node):
            #     if ref.on_delete == 'restrict':
            #         users = [(referrer_type, i) for i in ids]
            #         raise DeleteBlocked(node, users, _blocked_message(store, node, users, False))
            #     if ref.on_delete == 'set_null':
            #         for i in ids:
            #             adapter.update(referrer_type, i, {ref.field: None}, tx)
            #     else:                                    # cascade
            #         for i in ids:
            #             remove((referrer_type, i))
            # ↑ до 2026-11-01 (Ф1.6.3а): set_null обнулял ссылки, cascade удалял ссылающиеся
            #   записи — изменения БД, которых пользователь не отдавал; осталось одно правило
            for referrer_type, _ref, ids in users_of(node): # restrict — единственное правило
                users = [(referrer_type, i) for i in ids]
                raise DeleteBlocked(
                    node,                                           # удаляемая запись
                    users,                                          # кто на неё ссылается
                    _blocked_message(store, node, users, False),    # текст отказа
                )
        # adapter.delete(node[0], node[1], tx)
        # ↑ до 2026-10-31 (Ф1.3.4): цель ссылок, которую хранилище данных уже убрало в этой
        #   же транзакции (сервис сам удаляет ставшую ненужной общую заметку, когда запись
        #   сменила текст), удалялась ещё раз — «не найдено» и откат ВСЕГО сохранения.
        #   Теперь такая цель считается удалённой: удалять нечего.
        if not (schema.referrers(node[0]) and hasattr(adapter, 'read')
                and adapter.read(node[0], node[1], tx) is None):
            adapter.delete(node[0], node[1], tx)
        removed.append(node)
        # for ref in collected:
        #     target = (values or {}).get(ref.field)
        #     if target is None or (ref.entity, target) in visiting:
        #         continue
        #     still_used = any(
        #         any((t, i) not in visiting for i in adapter.referrers(t, r.field, [target], tx))
        #         for t, r in schema.referrers(ref.entity))
        #     if not still_used:
        #         remove((ref.entity, target))
        # ↑ до 2026-11-01 (Ф1.6.3а): collect — черновики сами удаляли из БД цель, на которую
        #   больше никто не ссылается (рекурсивно); уборка ненужного — хранилище данных
        #   (сервис), позже — сборщик по событиям таблиц

    for root in roots:
        remove(root)
    return removed


def execute_plan(
    store   : 'DraftStore',         # хранилище черновиков (то же, что у плана)
    plan    : SavePlan,             # план
    adapter : PersistenceAdapter,   # связь с хранилищем данных
) -> SaveResult:
    """
    Выполняет план в одной транзакции; при успехе убирает сохранённые черновики и
    заменяет временные id настоящими (в том числе у оставшихся черновиков детей).

    Перенесённые записи (``plan.moved_deletes``) удаляются так же, как помеченные: тем же
    ``adapter.delete`` в той же транзакции. Откат оставляет и запись, и её файл: файл убирает
    только хранилище данных и только после коммита.

    Args:
        store   : (DraftStore) Хранилище черновиков (то же, по которому строился план).
        plan    : (SavePlan) План (``build_plan``).
        adapter : (PersistenceAdapter) Связь с хранилищем данных.

    Returns:
        (SaveResult) Итог сохранения.

    Raises:
        PlanError: В плане остались новые предки вне объёма (не спросили пользователя);
            перенесённую запись в БД успели перенести мимо черновика.
        StalePlanError: Черновики изменились после построения плана.
        Exception: Любая ошибка адаптера — транзакция откатывается, черновики не
            меняются, исключение пробрасывается.

    Example:
        >>> execute_plan(
        ...     store,                      # хранилище
        ...     build_plan(store, None),    # план на всё
        ...     adapter,                    # связь с БД
        ... ).id_map
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
        #   С 2026-11-01 (Ф1.6.3а) снова удаляются только помеченные — с проверкой ссылок
        #   (отказ, если на удаляемую ссылаются); обнуления, каскада и уборки ненужного нет
        # removed = _delete_with_references(store, [d.key for d in plan.deletes], adapter, tx)
        # ↑ до 2026-11-07 (DR10): удалялись только помеченные; перенесённые записи идут вместе
        #   с ними снизу вверх — фото раньше приёма, который удалит его каскадом
        moved_present, moved_gone = _moved_still_in_place(
            store,                  # хранилище
            plan.moved_deletes,     # перенесённые записи
            adapter,                # связь с БД
            tx,                     # транзакция
        )
        present = set(moved_present)
        roots = sorted(
            (*plan.deletes, *(d for d in plan.moved_deletes if d.key in present)),
            key = lambda d: (-store.schema.depth(d.entity), d.order),    # снизу вверх
        )
        removed = _delete_with_references(store, [d.key for d in roots], adapter, tx)

    # deleted = tuple(d.key for d in plan.deletes)
    # deleted = tuple(removed)
    # ↑ до 2026-11-07 (DR10): записей, которых в БД уже нет, связи тоже надо забыть
    deleted = (*removed, *moved_gone)
    # store._commit(plan.consumed, id_map, removed=deleted)
    # ↑ до 2026-10-16: закрытый метод хранилища; теперь открытый apply_saved
    store.apply_saved(plan.consumed, id_map, removed=deleted)
    return SaveResult(
        id_map=id_map,
        created=tuple((d.entity, id_map[d.key]) for d in plan.creates),
        updated=tuple(d.key for d in plan.updates),
        deleted=deleted,
        dropped=tuple(d.key for d in plan.dropped),
        moved_deleted=tuple(d.key for d in plan.moved_deletes),
    )

