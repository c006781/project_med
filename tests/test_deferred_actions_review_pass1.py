# tests/test_deferred_actions_review_pass1.py

"""
Тесты исправлений проверки модуля app.utils.deferred_actions, проход 1 (2026-10-21).

Номера (DA1 …) — журнал проверок в ``app/utils/IMPLEMENTATION.md``.
"""

import functools
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.utils.deferred_actions as module
from app.utils.deferred_actions import (
    ActionContext,
    ActionType,
    action_name,
    add_deferred_action,
    clear_actions_by_type,
    execute_actions,
    get_actions_by_type,
)


@pytest.fixture
def no_qt_app():
    """Без приложения Qt — действия выполняются сразу."""
    with patch.object(module.QCoreApplication, 'instance', return_value=None):
        yield


def test_da1_no_logger_no_crash(no_qt_app):
    """logger=None — действие выполнено, ошибок журнала нет (раньше print.debug)."""
    done = []
    execute_actions([(done.append, (1,), {})])
    assert done == [1]


def test_da1_error_logged_others_run(no_qt_app):
    """Ошибка одного действия — в журнал, остальные выполняются."""
    logger = MagicMock()
    done = []

    def boom():
        raise RuntimeError('сбой')

    execute_actions([(boom, (), {}), (done.append, (2,), {})], logger=logger)
    assert done == [2]
    logger.exception.assert_called_once()
    assert 'boom' in logger.exception.call_args.args[0]


def test_da2_partial_success_not_error(no_qt_app):
    """partial — успешное действие не считается ошибкой (раньше f.__name__ → AttributeError)."""
    logger = MagicMock()
    done = []
    execute_actions([(functools.partial(done.append, 3), (), {})], logger=logger)
    assert done == [3]
    logger.exception.assert_not_called()


@pytest.mark.parametrize(
    'func, expected_start',
    [(len, 'len'), (functools.partial(len, 'x'), 'functools.partial'), (SimpleNamespace.__init__, 'SimpleNamespace')],
)
def test_da2_action_name(func, expected_start):
    """Имя действия для журнала."""
    assert action_name(func).startswith(expected_start)


def test_da2_action_name_callable_object():
    """Объект с __call__ без имени — repr."""
    class Callable:
        def __call__(self):
            pass
    obj = Callable()
    obj_name = action_name(obj)
    assert 'Callable' in obj_name


def test_da3_without_qt_app_runs_now(no_qt_app):
    """Без приложения Qt — сразу (раньше QTimer без цикла: никогда)."""
    done = []
    execute_actions([(done.append, (4,), {})])
    assert done == [4]


def test_da3_with_qt_app_runs_in_event_loop():
    """С приложением Qt — в цикле событий (не сразу), аргументы каждого действия свои."""
    code = (
        "import sys\n"
        "from PySide6.QtCore import QCoreApplication, QTimer\n"
        "app = QCoreApplication(sys.argv)\n"
        "from app.utils.deferred_actions import execute_actions\n"
        "done = []\n"
        "execute_actions([(done.append, (i,), {}) for i in range(3)])\n"
        "before = list(done)\n"
        "QTimer.singleShot(50, app.quit)\n"
        "app.exec()\n"
        "print(before, done)\n"
    )
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60,
                            env={'QT_QPA_PLATFORM': 'offscreen', 'PATH': ''}, cwd='.')
    assert result.stdout.strip().splitlines()[-1] == '[] [0, 1, 2]'


def test_add_deferred_action_queue_and_now():
    """Контекст — в очередь; без контекста — сразу."""
    session = SimpleNamespace()
    done = []
    add_deferred_action(ActionContext(session, ActionType.COMMIT), done.append, (1,))
    assert done == []
    assert get_actions_by_type(session, ActionType.COMMIT) == [(done.append, (1,), {})]
    clear_actions_by_type(session, ActionType.COMMIT)
    assert get_actions_by_type(session, ActionType.COMMIT) == []
    add_deferred_action(None, done.append, (2,))
    assert done == [2]


def test_action_context_bool():
    """Контекст без сессии/типа — ложный."""
    assert not ActionContext(None, ActionType.COMMIT)
    assert ActionContext(SimpleNamespace(), ActionType.ROLLBACK)


def test_empty_actions():
    """Пустой список — ничего."""
    execute_actions([])
