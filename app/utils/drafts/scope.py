# app/utils/drafts/scope.py

"""
Объём операции (сохранение, отмена, проверка «есть ли изменения»): цель × направления.

Цель — набор узлов: одна строка (узел ветки), выборка фрейма (несколько веток) или
``None`` — все черновики. Направления — флаги ``SaveScope``, сочетаются свободно
(IMPLEMENTATION.md §2.1 приложения, требование владельца).

Пример:
    >>> SaveScope.SELF | SaveScope.DESCENDANTS == SaveScope.BRANCH
    True
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Iterable, Optional, Set

from ._model import NodeKey

if TYPE_CHECKING:  # только для подсказок типов — без цикла импортов
    from .store import DraftStore


class SaveScope(enum.Flag):
    """
    Направления от узлов цели.

    * ``SELF`` — сами узлы цели;
    * ``DESCENDANTS`` — все их потомки (на любую глубину);
    * ``ANCESTORS`` — их предки, только сами предки (без других детей предков).

    Готовые сочетания: ``BRANCH`` (узел и потомки), ``PATH`` (предки и узел),
    ``FULL`` (предки, узел и потомки).

    Пример:
        >>> SaveScope.ANCESTORS in SaveScope.FULL
        True
    """

    SELF = enum.auto()
    DESCENDANTS = enum.auto()
    ANCESTORS = enum.auto()
    BRANCH = SELF | DESCENDANTS
    PATH = ANCESTORS | SELF
    FULL = ANCESTORS | SELF | DESCENDANTS


def select_nodes(
    store: 'DraftStore',
    targets: Optional[Iterable[NodeKey]],
    scope: SaveScope,
) -> Set[NodeKey]:
    """
    Узлы с черновиками, попадающие в объём.

    Возвращаются только узлы, у которых ЕСТЬ черновик: узлы без изменений сохранять и
    отменять нечего (предки/потомки без черновиков проходятся, но в результат не идут).

    Args:
        store: Хранилище черновиков.
        targets: Узлы цели; ``None`` — все черновики (направления не важны).
        scope: Направления.

    Returns:
        Множество ключей узлов.

    Пример:
        >>> select_nodes(store, [('appointment', 12)], SaveScope.BRANCH)
        {('appointment', 12), ('photo', -1)}
    """
    if targets is None:
        return set(store.drafted_nodes())
    result: Set[NodeKey] = set()
    for node in targets:
        if SaveScope.SELF in scope:
            result.add(node)
        if SaveScope.DESCENDANTS in scope:
            result.update(store.descendants(node))
        if SaveScope.ANCESTORS in scope:
            result.update(store.ancestors(node))
    return {node for node in result if store.has_draft(*node)}
