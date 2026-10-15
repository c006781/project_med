# app/utils/drafts/conflicts.py

"""
Конфликты: запись изменилась в хранилище данных (БД), пока лежал черновик.

Черновик существующей записи помнит исходные значения изменённых полей (``original``).
Перед сохранением их можно сравнить с текущими значениями в БД: другой пользователь,
синхронизация или импорт могли поменять ту же запись. Пакет только сообщает о
конфликтах — решает вызывающий (спросить пользователя, перечитать, сохранить поверх).

Пример:
    >>> plan = build_plan(store)
    >>> conflicts = find_conflicts(plan, read=adapter.read)
    >>> if conflicts: ...   # показать пользователю
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Hashable, List, Mapping, Optional

from ._model import NodeKey
from .plan import SavePlan

# Чтение текущей записи из хранилища данных: (тип, id) -> поля или None (записи нет)
Reader = Callable[[str, Hashable], Optional[Mapping[str, Any]]]


@dataclass(frozen=True)
class Conflict:
    """
    Расхождение черновика с хранилищем данных.

    Attributes:
        node: Узел.
        field: Поле; ``None`` — записи в хранилище больше нет.
        original: Значение, от которого отталкивался черновик.
        current: Значение в хранилище сейчас.
        draft: Значение в черновике (для удаления — ``None``).

    Пример:
        >>> Conflict(('appointment', 12), 'cost', 400, 450, 500)
    """

    node: NodeKey
    field: Optional[str]
    original: Any = None
    current: Any = None
    draft: Any = None

    @property
    def record_gone(self) -> bool:
        """
        Записи в хранилище данных больше нет.

        Returns:
            ``True``, если удалена.

        Пример:
            >>> Conflict(('photo', 7), None).record_gone
            True
        """
        return self.field is None


def find_conflicts(plan: SavePlan, read: Reader) -> List[Conflict]:
    """
    Конфликты для изменяемых и удаляемых существующих записей плана.

    Сравниваются только поля с известным исходным значением (``Draft.original``); новые
    записи не проверяются (их ещё нет в хранилище). Ошибка чтения — исключение
    вызывающему (проверка не должна молча пропускать конфликты).

    Args:
        plan: План сохранения.
        read: Чтение текущей записи; ``None`` — записи нет.

    Returns:
        Список конфликтов (пустой — можно сохранять).

    Пример:
        >>> find_conflicts(plan, lambda t, i: {'cost': 450})
        [Conflict(node=('appointment', 12), field='cost', original=400, current=450, draft=500)]
    """
    conflicts: List[Conflict] = []
    for draft in (*plan.updates, *plan.deletes):
        current = read(draft.entity, draft.id)
        if current is None:
            conflicts.append(Conflict(draft.key, None))
            continue
        for field, original in draft.original.items():
            if field not in draft.data and not draft.deleted:
                continue              # поле вернули к исходному — не важно, что в БД
            if current.get(field) != original:
                conflicts.append(Conflict(draft.key, field, original, current.get(field),
                                          None if draft.deleted else draft.data.get(field)))
    return conflicts
