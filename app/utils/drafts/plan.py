# app/utils/drafts/plan.py

"""
План сохранения: какие записи создать, изменить, удалить и в каком порядке.

План строится без БД и без интерфейса — чистая функция от хранилища, цели и
направлений. Интерфейс по плану задаёт вопросы (новые предки вне объёма, удаляемые
ветки), затем отдаёт план исполнителю (``executor.execute_plan``).

Пример:
    >>> plan = build_plan(store, targets=[('appointment', 12)], scope=SaveScope.BRANCH)
    >>> if plan.missing_new_ancestors:
    ...     plan = build_plan(store, [('appointment', 12)], SaveScope.BRANCH,
    ...                       include_new_ancestors=True)      # пользователь согласился
    >>> plan.deleted_branches                                  # спросить подтверждение
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from ._model import DeleteBlocked, Draft, NodeKey, PlanError
from .policies import CascadeDeletePolicy, DeletePolicy
from .scope import SaveScope, select_nodes

if TYPE_CHECKING:
    from .store import DraftStore


@dataclass(frozen=True)
class SavePlan:
    """
    План сохранения (неизменяемый).

    Attributes:
        creates: Новые записи — сверху вниз по дереву (родитель раньше детей).
        updates: Изменения существующих записей.
        deletes: Удаляемые существующие записи — снизу вверх.
        dropped: Черновики, поглощаемые без записи (внутри удаляемых веток).
        deleted_branches: Корни удаляемых веток — показать пользователю.
        blocked: Выбранные узлы, не попавшие в план: их предок удаляется, но не
            входит в объём.
        missing_new_ancestors: Новые (не в БД) предки сохраняемых записей вне
            объёма. Пока список не пуст, план не исполняется: спросить пользователя и
            построить заново с ``include_new_ancestors=True`` (требование 6).
        version: Версия хранилища при построении (устаревший план не исполняется).
        store_token: Метка хранилища, по которому построен план (F2: план другого
            хранилища не исполняется, даже если номера версий совпали).

    Пример:
        >>> plan.is_empty, plan.needs_confirmation
        (False, True)
    """

    creates: Tuple[Draft, ...] = ()
    updates: Tuple[Draft, ...] = ()
    deletes: Tuple[Draft, ...] = ()
    dropped: Tuple[Draft, ...] = ()
    deleted_branches: Tuple[NodeKey, ...] = ()
    blocked: Tuple[NodeKey, ...] = ()
    missing_new_ancestors: Tuple[NodeKey, ...] = ()
    version: int = 0
    store_token: object = None

    @property
    def is_empty(self) -> bool:
        """
        Нечего сохранять и нечего поглощать.

        Returns:
            ``True``, если план пуст.

        Пример:
            >>> SavePlan().is_empty
            True
        """
        return not (self.creates or self.updates or self.deletes or self.dropped)

    @property
    def needs_confirmation(self) -> bool:
        """
        Нужен вопрос пользователю: новые предки вне объёма или удаляемые ветки.

        Returns:
            ``True``, если нужен.

        Пример:
            >>> SavePlan().needs_confirmation
            False
        """
        return bool(self.missing_new_ancestors or self.deleted_branches)

    @property
    def consumed(self) -> FrozenSet[NodeKey]:
        """
        Узлы, чьи черновики будут убраны из хранилища после успешного сохранения.

        Returns:
            Множество ключей.

        Пример:
            >>> ('photo', -1) in plan.consumed
            True
        """
        return frozenset(d.key for group in (self.creates, self.updates, self.deletes, self.dropped)
                         for d in group)


def _dependencies(store: 'DraftStore', node: NodeKey) -> List[NodeKey]:
    """
    От каких записей зависит запись при создании: родитель и цели ссылок (по итоговым
    значениям черновика).

    Args:
        store: Хранилище.
        node: Узел.

    Returns:
        Узлы (могут быть и сохранённые в БД — их отберёт вызывающий).

    Пример:
        >>> _dependencies(store, ('appointment', -2))
        [('patient', -1), ('doctor', -3)]
    """
    result: List[NodeKey] = []
    parent = store.parent_of(*node)
    if parent is not None:
        result.append(parent)
    draft = store.get(*node)
    data = draft.data if draft is not None else {}
    for ref in store.schema.references(node[0]):
        value = data.get(ref.field)
        if value is not None:
            result.append((ref.entity, value))
    return result


def _check_deleted_new_targets(store: 'DraftStore', writable: Set[NodeKey]) -> None:
    """
    Сохраняемая запись ссылается на НОВУЮ запись, которую удалили (она так и не будет
    создана), — понятный отказ, а не вопрос «сохранить и новую?» с непонятной ошибкой после
    согласия (2026-10-18).

    Args:
        store: Хранилище.
        writable: Сохраняемые узлы.

    Returns:
        None

    Raises:
        DeleteBlocked: Есть такие ссылки (цель — удалённая новая запись).

    Пример:
        >>> _check_deleted_new_targets(store, {('appointment', -2)})
        Traceback (most recent call last):
        DeleteBlocked: Нельзя удалить «Врач #-1»: на неё ссылаются несохранённые изменения: «Приём #-2»
    """
    from .executor import _blocked_message           # здесь: executor импортирует этот модуль
    users: Dict[NodeKey, List[NodeKey]] = {}
    for node in sorted(writable, key=lambda n: store.get(*n).order):
        parent = store.parent_of(*node)
        for dep in _dependencies(store, node):
            if dep == parent:
                continue                               # родитель — забота политики удаления
            draft = store.get(*dep)
            if draft is not None and draft.is_new and draft.deleted:
                users.setdefault(dep, []).append(node)
    for target, referrers in users.items():
        raise DeleteBlocked(target, referrers, _blocked_message(store, target, referrers, True))


def _required_new(store: 'DraftStore', writable: Set[NodeKey]) -> List[NodeKey]:
    """
    Новые записи вне объёма, без которых сохраняемые записать нельзя: новые предки и
    новые цели ссылок — рекурсивно (у новой цели свои новые предки и ссылки).

    Args:
        store: Хранилище.
        writable: Сохраняемые узлы.

    Returns:
        Узлы по порядку появления.

    Пример:
        >>> _required_new(store, {('appointment', -2)})
        [('doctor', -3)]
    """
    missing: List[NodeKey] = []
    queue = sorted(writable, key=lambda n: store.get(*n).order)
    while queue:
        node = queue.pop(0)
        candidates = list(store.ancestors(node)) + [d for d in _dependencies(store, node)
                                                    if d not in store.ancestors(node)]
        for dep in candidates:
            draft = store.get(*dep)
            if draft is None or not draft.is_new or dep in writable or dep in missing:
                continue
            missing.append(dep)
            queue.append(dep)
    return missing


def _ordered_creates(store: 'DraftStore', creates: List[Draft], depth: Callable[[NodeKey], int]) -> List[Draft]:
    """
    Порядок создания: запись — после всех новых записей, от которых она зависит (родитель,
    цели ссылок); среди готовых — по глубине дерева и порядку появления.

    Args:
        store: Хранилище.
        creates: Новые записи плана.
        depth: Функция глубины узла.

    Returns:
        Упорядоченный список.

    Raises:
        PlanError: Новые записи ссылаются друг на друга по кругу.

    Пример:
        >>> [d.key for d in _ordered_creates(store, creates, depth)]
        [('doctor', -3), ('patient', -1), ('appointment', -2)]
    """
    pending = {d.key: d for d in creates}
    done: List[Draft] = []
    placed: Set[NodeKey] = set()
    while pending:
        ready = [d for d in pending.values()
                 if all(dep in placed or dep not in pending for dep in _dependencies(store, d.key))]
        if not ready:
            raise PlanError("новые записи ссылаются друг на друга по кругу: "
                            + ", ".join(f"{t}:{i}" for t, i in sorted(pending, key=str)))
        ready.sort(key=lambda d: (depth(d.key), d.order))
        first = ready[0]
        done.append(first)
        placed.add(first.key)
        del pending[first.key]
    return done


def build_plan(
    store: 'DraftStore',
    targets: Optional[Iterable[NodeKey]] = None,
    scope: SaveScope = SaveScope.BRANCH,
    delete_policy: Optional[DeletePolicy] = None,
    include_new_ancestors: bool = False,
) -> SavePlan:
    """
    Строит план сохранения для объёма (цель × направления).

    Шаги:
        1. Узлы с черновиками в объёме (``select_nodes``).
        2. Политика удаления: удаляемые ветки, поглощаемые черновики, заблокированные узлы.
        3. Новые предки сохраняемых записей вне объёма → ``missing_new_ancestors``
           (или добавляются, если ``include_new_ancestors``; добавляются ТОЛЬКО сами
           предки, без их других детей).
        4. Порядок: создание сверху вниз, удаление снизу вверх; внутри уровня — порядок
           появления черновиков.

    Args:
        store: Хранилище.
        targets: Узлы цели (строка — один узел, фрейм — его выборка); ``None`` — всё.
        scope: Направления (``SaveScope``).
        delete_policy: Политика удаления; по умолчанию ``CascadeDeletePolicy``.
        include_new_ancestors: Добавить в план новых предков вне объёма.

    Returns:
        План.

    Raises:
        PlanError: Политика удаления запретила сохранение.

    Пример:
        >>> build_plan(store, None).is_empty          # сохранить всё
        False
    """
    policy = delete_policy or CascadeDeletePolicy()
    selected: Set[NodeKey] = select_nodes(store, targets, scope)
    resolution = policy.resolve(store, selected)
    # F3 (проверка ядра 2): решение политики проверяется — ошибочная политика не должна
    # удалить из БД запись, которую никто не помечал, или подсунуть узел без черновика.
    for node in (*resolution.deletes, *resolution.dropped, *resolution.blocked):
        if not store.has_draft(*node):
            raise PlanError(f"политика удаления вернула узел без черновика: {node[0]}:{node[1]}")
    for node in resolution.deletes:
        draft = store.get(*node)
        if not draft.deleted or draft.is_new:
            raise PlanError(
                f"политика удаления хочет удалить из БД {node[0]}:{node[1]}, "
                "но запись не помечена на удаление или ещё не сохранена"
            )
    by_delete = set(resolution.deletes) | set(resolution.dropped)
    writable = selected - by_delete - set(resolution.blocked)
    # F1 (проверка ядра 1): гарантии НЕ зависят от политики — помеченное на удаление
    # никогда не создаётся и не изменяется, а потомок удаляемой записи вне её ветки не
    # пишется. Раньше это полностью доверялось политике: своя политика могла пропустить
    # удалённую запись в creates/updates.
    unhandled = [n for n in writable if store.get(*n).deleted]
    if unhandled:
        raise PlanError(
            "политика удаления не обработала записи, помеченные на удаление: "
            + ", ".join(f"{t}:{i}" for t, i in sorted(unhandled, key=str))
        )
    extra_blocked = [n for n in writable
                     if any((a := store.get(*x)) is not None and a.deleted for x in store.ancestors(n))]
    writable.difference_update(extra_blocked)
    blocked = tuple(resolution.blocked) + tuple(n for n in extra_blocked if n not in resolution.blocked)

    # missing: List[NodeKey] = []
    # for node in sorted(writable, key=lambda n: store.get(*n).order):
    #     for ancestor in store.ancestors(node):
    #         draft = store.get(*ancestor)
    #         if draft is None or not draft.is_new or ancestor in writable or ancestor in missing:
    #             continue
    #         missing.append(ancestor)
    # ↑ до 2026-10-18: нужными считались только новые ПРЕДКИ. Теперь ещё и новые записи, на
    #   которые ссылаются (ссылки, не владение: приём → новый врач) — и их предки, рекурсивно.
    _check_deleted_new_targets(store, writable)
    missing = _required_new(store, writable)
    if include_new_ancestors:
        writable.update(missing)
        missing = []

    def depth(node: NodeKey) -> int:
        """
        Глубина узла по схеме (для порядка: родители раньше детей).

        Args:
            node: Узел.

        Returns:
            Глубина типа узла.

        Пример:
            >>> depth(('photo', 7))
            2
        """
        return store.schema.depth(node[0])

    drafts = {node: store.get(*node) for node in writable | by_delete}
    # creates = sorted((drafts[n] for n in writable if drafts[n].is_new),
    #                  key=lambda d: (depth(d.key), d.order))
    # ↑ до 2026-10-18: порядок по глубине дерева; теперь ещё и запись, на которую
    #   ссылаются, — раньше ссылающейся (её настоящий id нужен в ссылке)
    creates = _ordered_creates(store, [drafts[n] for n in writable if drafts[n].is_new], depth)
    updates = sorted((drafts[n] for n in writable if not drafts[n].is_new),
                     key=lambda d: (depth(d.key), d.order))
    deletes = sorted((drafts[n] for n in resolution.deletes),
                     key=lambda d: (-depth(d.key), d.order))
    dropped = [drafts[n] for n in resolution.dropped]
    return SavePlan(
        creates=tuple(creates), updates=tuple(updates), deletes=tuple(deletes),
        dropped=tuple(dropped), deleted_branches=resolution.branches,
        blocked=blocked, missing_new_ancestors=tuple(missing),
        version=store.version, store_token=store.token,
    )
