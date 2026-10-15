# app/utils/drafts/policies.py

"""
Политики удаления: что делать при сохранении с веткой под записью, помеченной на
удаление.

Политика — отдельный объект, его можно заменить, не трогая хранилище и план
(требование 7 владельца: «сделать так, чтобы в дальнейшем можно было поменять»).

* ``CascadeDeletePolicy`` (по умолчанию) — удаляется вся ветка, черновики потомков
  отбрасываются; ветки перечисляются в плане для подтверждения.
* ``RejectChildChangesPolicy`` — удалять нельзя, пока у потомков есть изменения
  (кроме тех, что сами помечены на удаление).

Своя политика — любой объект с методом ``resolve(store, selected)`` (см. ``DeletePolicy``).

Пример:
    >>> plan = build_plan(store, delete_policy=RejectChildChangesPolicy())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Set, Tuple

from ._model import NodeKey, PlanError

try:  # Protocol — с Python 3.8
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore

if TYPE_CHECKING:
    from .store import DraftStore


@dataclass(frozen=True)
class DeleteResolution:
    """
    Решение политики удаления для выбранных узлов.

    Attributes:
        deletes: Существующие записи, которые удаляются из БД (корни удаляемых веток;
            потомков в БД удаляет хранилище данных — каскад БД или адаптер).
        dropped: Черновики, которые поглощаются без записи (новые удалённые записи,
            изменения внутри удаляемых веток).
        branches: Корни удаляемых веток — для диалога подтверждения.
        blocked: Выбранные узлы, которые НЕ сохраняются: их предок помечен на
            удаление, но в объём сохранения не входит (сохранять изменения записи,
            которую скоро удалят вместе с веткой, бессмысленно).

    Пример:
        >>> DeleteResolution((('appointment', 12),), (('photo', 3),), (('appointment', 12),), ())
    """

    deletes: Tuple[NodeKey, ...] = ()
    dropped: Tuple[NodeKey, ...] = ()
    branches: Tuple[NodeKey, ...] = ()
    blocked: Tuple[NodeKey, ...] = ()


class DeletePolicy(Protocol):
    """
    Интерфейс политики удаления.

    Пример:
        >>> class MyPolicy:
        ...     def resolve(self, store, selected): return DeleteResolution()
    """

    def resolve(self, store: 'DraftStore', selected: Set[NodeKey]) -> DeleteResolution:
        """
        Решает, что делать с помеченными на удаление узлами из ``selected``.

        Args:
            store: Хранилище черновиков.
            selected: Узлы с черновиками, попавшие в объём сохранения.

        Returns:
            Решение.

        Raises:
            PlanError: Политика запрещает такое сохранение.

        Пример:
            >>> CascadeDeletePolicy().resolve(store, {('appointment', 12)})
        """
        ...  # pragma: no cover


def _deleted_roots(store: 'DraftStore', selected: Set[NodeKey]) -> List[NodeKey]:
    """
    Верхние удаляемые узлы: помечены на удаление и нет выбранного удаляемого предка.

    Args:
        store: Хранилище.
        selected: Выбранные узлы.

    Returns:
        Узлы в порядке появления черновиков.

    Пример:
        >>> _deleted_roots(store, {('appointment', 12), ('photo', 3)})
        [('appointment', 12)]
    """
    deleted = {n for n in selected if store.get(*n).deleted}
    roots = [n for n in deleted if not any(a in deleted for a in store.ancestors(n))]
    return sorted(roots, key=lambda n: store.get(*n).order)


class CascadeDeletePolicy:
    """
    Удаление ветки целиком (по умолчанию).

    Для каждого верхнего удаляемого узла: сам узел — в ``deletes`` (если он есть в БД)
    или в ``dropped`` (новый); все черновики его потомков — в ``dropped``.

    Пример:
        >>> CascadeDeletePolicy().resolve(store, {('appointment', 12)}).branches
        (('appointment', 12),)
    """

    def resolve(self, store: 'DraftStore', selected: Set[NodeKey]) -> DeleteResolution:
        """
        См. ``DeletePolicy.resolve``.

        Args:
            store: Хранилище.
            selected: Выбранные узлы.

        Returns:
            Решение.

        Пример:
            >>> CascadeDeletePolicy().resolve(store, set())
            DeleteResolution(deletes=(), dropped=(), branches=(), blocked=())
        """
        roots = _deleted_roots(store, selected)
        deletes: List[NodeKey] = []
        dropped: List[NodeKey] = []
        covered: Set[NodeKey] = set()
        for root in roots:
            draft = store.get(*root)
            (dropped if draft.is_new else deletes).append(root)
            covered.add(root)
            for node in store.descendants(root):
                if store.has_draft(*node) and node not in covered:
                    dropped.append(node)
                    covered.add(node)
        blocked = []
        for node in selected - covered:
            if any((a_draft := store.get(*a)) is not None and a_draft.deleted
                   for a in store.ancestors(node)):
                blocked.append(node)
        order = lambda n: store.get(*n).order  # noqa: E731 — сортировка по порядку появления
        return DeleteResolution(
            deletes=tuple(deletes),
            dropped=tuple(sorted(dropped, key=order)),
            branches=tuple(roots),
            blocked=tuple(sorted(blocked, key=order)),
        )


class RejectChildChangesPolicy(CascadeDeletePolicy):
    """
    Как ``CascadeDeletePolicy``, но запрещает удаление ветки, в которой есть
    несохранённые изменения потомков (не помеченных на удаление): сначала их нужно
    сохранить или отменить.

    Пример:
        >>> RejectChildChangesPolicy().resolve(store, {('appointment', 12)})
        Traceback (most recent call last):
        PlanError: ...
    """

    def resolve(self, store: 'DraftStore', selected: Set[NodeKey]) -> DeleteResolution:
        """
        См. ``DeletePolicy.resolve``.

        Args:
            store: Хранилище.
            selected: Выбранные узлы.

        Returns:
            Решение (как у каскада).

        Raises:
            PlanError: В удаляемой ветке есть изменения потомков.

        Пример:
            >>> RejectChildChangesPolicy().resolve(store, set())
            DeleteResolution(deletes=(), dropped=(), branches=(), blocked=())
        """
        resolution = super().resolve(store, selected)
        conflicts = [n for n in resolution.dropped
                     if n not in resolution.branches and not store.get(*n).deleted]
        if conflicts:
            raise PlanError(
                "в удаляемых ветках есть несохранённые изменения: "
                + ", ".join(f"{t}:{i}" for t, i in conflicts)
            )
        return resolution
