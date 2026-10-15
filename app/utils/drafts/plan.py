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
from typing import TYPE_CHECKING, FrozenSet, Iterable, List, Optional, Set, Tuple

from ._model import Draft, NodeKey
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
    by_delete = set(resolution.deletes) | set(resolution.dropped)
    writable = selected - by_delete - set(resolution.blocked)

    missing: List[NodeKey] = []
    for node in sorted(writable, key=lambda n: store.get(*n).order):
        for ancestor in store.ancestors(node):
            draft = store.get(*ancestor)
            if draft is None or not draft.is_new or ancestor in writable or ancestor in missing:
                continue
            missing.append(ancestor)
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
    creates = sorted((drafts[n] for n in writable if drafts[n].is_new),
                     key=lambda d: (depth(d.key), d.order))
    updates = sorted((drafts[n] for n in writable if not drafts[n].is_new),
                     key=lambda d: (depth(d.key), d.order))
    deletes = sorted((drafts[n] for n in resolution.deletes),
                     key=lambda d: (-depth(d.key), d.order))
    dropped = [drafts[n] for n in resolution.dropped]
    return SavePlan(
        creates=tuple(creates), updates=tuple(updates), deletes=tuple(deletes),
        dropped=tuple(dropped), deleted_branches=resolution.branches,
        blocked=resolution.blocked, missing_new_ancestors=tuple(missing),
        version=store.version,
    )
