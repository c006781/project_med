# tests/test_deferred_actions_review_pass2.py

"""
Тесты проверки модуля app.utils.deferred_actions, проход 2 (2026-10-25).

Номера (DA4 …) — журнал проверок в ``app/utils/IMPLEMENTATION.md``.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text

import app.utils.deferred_actions as module
from app.utils.deferred_actions import (
    ActionContext,
    ActionType,
    add_deferred_action,
    get_actions_by_type,
)


@pytest.fixture
def no_qt_app():
    """Без приложения Qt — действия выполняются сразу (а не в цикле событий)."""
    with patch.object(
        module.QCoreApplication,  # класс приложения Qt
        'instance',               # «есть ли приложение»
        return_value = None,      # нет
    ):
        yield


@pytest.fixture
def db(tmp_path: Path):
    """Временная база (scoped_session — одна сессия на поток, как в программе)."""
    from app.database.database import Database

    database = Database(
        f"sqlite:///{(tmp_path / 't.db').as_posix()}",
    )
    yield database
    database.close()


# ---------------------------------------------------------------------------
# DA4 — описание: контекст истинен и при неактивной сессии
# ---------------------------------------------------------------------------

def test_da4_bool_does_not_check_is_active() -> None:
    """Истинность контекста — «сессия и тип заданы»; активность сессии не проверяется."""
    session = SimpleNamespace(is_active=False)
    assert ActionContext(session, ActionType.COMMIT)


def test_da4_inactive_session_still_queued() -> None:
    """Неактивная сессия — действие всё равно в очередь (а не сразу)."""
    session = SimpleNamespace(is_active=False)
    done = []
    add_deferred_action(
        ActionContext(session, ActionType.COMMIT), # контекст
        done.append,                               # действие
        (1,),                                      # его аргументы
    )
    assert done == []
    assert len(get_actions_by_type(session, ActionType.COMMIT)) == 1


# ---------------------------------------------------------------------------
# DA5 — списки действий переживали свою транзакцию (обработчики app/database/database.py;
# то же, что FD9 для удалений). Исправлено 2026-10-30 (ТД-9) — пометка xfail снята;
# действия «при откате» после коммита — tests/test_database_shema/test_session_lists.py.
# ---------------------------------------------------------------------------

# @pytest.mark.xfail(
#     strict = True,
#     reason = 'DA5: after_rollback не очищает список COMMIT (app/database/database.py)',
# )
# ↑ до 2026-10-30 (ТД-9): ошибка исправлена в app/database/database.py
def test_da5_commit_actions_dropped_after_rollback(
    no_qt_app,  # действия — сразу
    db,         # временная база
) -> None:
    """Действие «после коммита» из откатившейся транзакции не выполняется следующим коммитом."""
    done = []

    with pytest.raises(RuntimeError):
        with db.session_scope() as session:
            session.execute(text('SELECT 1'))
            add_deferred_action(
                ActionContext(session, ActionType.COMMIT), # после коммита
                done.append,                               # действие
                ('откатившаяся',),                         # его аргументы
            )
            raise RuntimeError('ошибка сохранения')

    with db.session_scope() as session:  # другая, успешная транзакция того же потока
        session.execute(text('SELECT 1'))

    assert done == [], 'действие откатившейся транзакции выполнено чужим коммитом'
