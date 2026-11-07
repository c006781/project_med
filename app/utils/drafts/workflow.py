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
    store                 : DraftStore,                         # хранилище черновиков
    adapter               : PersistenceAdapter,                 # связь с БД
    targets               : Optional[Iterable[NodeKey]] = None, # узлы цели; None — всё
    scope                 : Optional[SaveScope] = None,         # направления; None — BRANCH
    confirm_new_ancestors : Optional[Confirm] = None,           # «сохранить и новых родителей?»
    confirm_deletes       : Optional[Confirm] = None,           # «удалить эти ветки?»
    delete_policy         : Optional[DeletePolicy] = None,      # политика удаления; None — каскад
) -> Optional[SaveResult]:
    """
    Сохраняет черновики с вопросами пользователю:

        1. План для цели × направлений.
        2. Новые предки вне объёма (треб. 6) — ``confirm_new_ancestors(plan)``; согласие —
           план строится заново с ними, отказ — сохранение отменяется (``None``).
        3. Удаляемые ветки (треб. 7) и судьба записей, перенесённых в удалённую новую запись
           (при любом значении ``MovedRule``), — ``confirm_deletes(plan)``; отказ — отмена.
        4. Исполнение одной транзакцией.

    Вопрос не задаётся, если функция не передана: без ``confirm_new_ancestors`` новые
    предки вне объёма — отмена (``None``); без ``confirm_deletes`` удаление считается
    подтверждённым (вызывающий сам отвечает за вопрос). Исключение — перенесённые записи
    (``plan.moved_deletes``): их пользователь на удаление не помечал, поэтому без вопроса
    сохранение отменяется (``None``), записи не удаляются молча.

    Args:
        store                 : (DraftStore) Хранилище черновиков.
        adapter               : (PersistenceAdapter) Связь с БД.
        targets               : (Iterable[NodeKey]/None) Узлы цели; None — всё.
        scope                 : (SaveScope/None) Направления; None — ``SaveScope.BRANCH``.
        confirm_new_ancestors : (Confirm/None) Вопрос «сохранить и новых родителей?».
        confirm_deletes       : (Confirm/None) Вопрос «удалить эти ветки?».
        delete_policy         : (DeletePolicy/None) Политика удаления; None — каскад.

    Returns:
        (SaveResult/None) Итог сохранения; None — пользователь отказался (нечего сохранять —
            пустой ``SaveResult``).

    Raises:
        PlanError: Политика удаления запретила сохранение; перенесённую запись в БД успели
            перенести мимо черновика (откат).
        Exception: Ошибка БД (транзакция откатана, черновики на месте).

    Example:
        >>> save_with_confirmation(
        ...     store,                                  # хранилище
        ...     adapter,                                # связь с БД
        ...     [('appointment', 12)],                  # цель
        ...     SaveScope.BRANCH,                       # с потомками
        ...     confirm_new_ancestors   =   ask_user,   # вопрос про родителей
        ...     confirm_deletes         =   ask_user,   # вопрос про удаление
        ... )
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
    # if plan.deleted_branches and confirm_deletes is not None and not confirm_deletes(plan):
    # ↑ до 2026-11-07 (DR10): без удаляемых веток вопроса не было, а перенесённая запись теперь
    #   удаляется и тогда, когда удалённая новая запись не входит в объём
    if plan.needs_delete_confirmation and confirm_deletes is not None and not confirm_deletes(plan):
        return None
    if plan.moved_deletes and confirm_deletes is None:
        return None
    if plan.is_empty:
        return SaveResult()
    # План перестраивается непосредственно перед записью: пока были открыты диалоги,
    # черновики могли измениться. Если изменился состав удаляемых веток или новых
    # предков — спрашиваем заново (рекурсия не глубже числа изменений пользователя).
    final = build_plan(store, targets, scope, delete_policy, include_new_ancestors=include)
    if (final.deleted_branches != plan.deleted_branches
            or final.missing_new_ancestors != plan.missing_new_ancestors
            or final.moved_deletes != plan.moved_deletes
            or final.moved_kept != plan.moved_kept):
        return save_with_confirmation(store, adapter, targets, scope,
                                      confirm_new_ancestors, confirm_deletes, delete_policy)
    return execute_plan(store, final, adapter)
