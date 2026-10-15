# app/utils/drafts/workflow.py

"""
Сценарий сохранения с вопросами пользователю: новые родители вне объёма, удаляемые
ветки, перестроение плана перед записью.

Вопросы передаются функциями (``Confirm``) — сценарий не зависит от интерфейса (Qt,
консоль, веб) и тестируется без окна. (До 2026-10-16 жил в ``app/draft/integration.py``;
перенесён в пакет — в нём нет ничего от приложения.)

Пример:
    >>> save_with_confirmation(store, adapter, [('appointment', 12)], SaveScope.BRANCH,
    ...                        confirm_new_ancestors=ask, confirm_deletes=ask)
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from ._model import NodeKey
from .executor import PersistenceAdapter, SaveResult, execute_plan
from .plan import SavePlan, build_plan
from .policies import DeletePolicy
from .scope import SaveScope
from .store import DraftStore

# Вопрос пользователю: получает план, возвращает True — согласен
Confirm = Callable[[SavePlan], bool]


def save_with_confirmation(
    store: DraftStore,
    adapter: PersistenceAdapter,
    targets: Optional[Iterable[NodeKey]] = None,
    scope: Optional[SaveScope] = None,
    confirm_new_ancestors: Optional[Confirm] = None,
    confirm_deletes: Optional[Confirm] = None,
    delete_policy: Optional[DeletePolicy] = None,
) -> Optional[SaveResult]:
    """
    Сохранение с вопросами пользователю:

        1. План для цели × направлений.
        2. Новые предки вне объёма (треб. 6) — ``confirm_new_ancestors(plan)``; согласие —
           план строится заново с ними, отказ — сохранение отменяется (``None``).
        3. Удаляемые ветки (треб. 7) — ``confirm_deletes(plan)``; отказ — отмена.
        4. Исполнение одной транзакцией.

    Вопрос не задаётся, если функция не передана: без ``confirm_new_ancestors`` новые
    предки вне объёма — отмена (``None``); без ``confirm_deletes`` удаление считается
    подтверждённым (вызывающий сам отвечает за вопрос).

    Args:
        store: Хранилище черновиков.
        adapter: Связь с БД.
        targets: Узлы цели; ``None`` — всё.
        scope: Направления; по умолчанию ``SaveScope.BRANCH``.
        confirm_new_ancestors: Вопрос «сохранить и новых родителей?».
        confirm_deletes: Вопрос «удалить эти ветки?».
        delete_policy: Политика удаления (по умолчанию — каскад).

    Returns:
        Итог сохранения; ``None`` — пользователь отказался (или нечего сохранять —
        тогда пустой ``SaveResult``).

    Raises:
        PlanError: Политика удаления запретила сохранение.
        Exception: Ошибка БД (транзакция откатана, черновики на месте).

    Пример:
        >>> save_with_confirmation(store, adapter, [('appointment', 12)], SaveScope.BRANCH,
        ...                        confirm_new_ancestors=ask_user, confirm_deletes=ask_user)
    """
    scope = SaveScope.BRANCH if scope is None else scope
    targets = None if targets is None else list(targets)
    include = False
    plan = build_plan(store, targets, scope, delete_policy)
    if plan.missing_new_ancestors:
        if confirm_new_ancestors is None or not confirm_new_ancestors(plan):
            return None
        include = True
        plan = build_plan(store, targets, scope, delete_policy, include_new_ancestors=True)
    if plan.deleted_branches and confirm_deletes is not None and not confirm_deletes(plan):
        return None
    if plan.is_empty:
        return SaveResult()
    # План перестраивается непосредственно перед записью: пока были открыты диалоги,
    # черновики могли измениться. Если изменился состав удаляемых веток или новых
    # предков — спрашиваем заново (рекурсия не глубже числа изменений пользователя).
    final = build_plan(store, targets, scope, delete_policy, include_new_ancestors=include)
    if (final.deleted_branches != plan.deleted_branches
            or final.missing_new_ancestors != plan.missing_new_ancestors):
        return save_with_confirmation(store, adapter, targets, scope,
                                      confirm_new_ancestors, confirm_deletes, delete_policy)
    return execute_plan(store, final, adapter)
