# tests/test_drafts/test_save_flow_and_qt.py

"""
Сохранение с вопросами пользователю (``save_with_confirmation``) и мост в Qt
(``DraftsQtBridge``) — без окна: вопросы — функции, QObject работает без QApplication.
"""

import pytest

from app.draft.integration import save_with_confirmation
from app.utils.drafts import SaveScope
from interfaces.gui.gui_window.drafts_qt import DraftsQtBridge


class Asker:
    """Ответчик на вопросы: запоминает, о чём спросили, и отвечает заданным."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked = []

    def __call__(self, plan) -> bool:
        self.asked.append(plan)
        return self.answer


# ---------------------------------------------------------------------------
# save_with_confirmation
# ---------------------------------------------------------------------------

def test_new_ancestors_declined_cancels(store, adapter):
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    ask = Asker(False)
    assert save_with_confirmation(store, adapter, [('photo', p)], SaveScope.SELF,
                                  confirm_new_ancestors=ask) is None
    assert ask.asked[0].missing_new_ancestors == (('appointment', a),)
    assert adapter.rows == {} and len(store.drafted_nodes()) == 2


def test_new_ancestors_accepted_saves_from_parents(store, adapter):
    """Треб. 6: при согласии сохраняется начиная от родителей."""
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    result = save_with_confirmation(store, adapter, [('photo', p)], SaveScope.SELF,
                                    confirm_new_ancestors=Asker(True))
    assert set(result.id_map) == {('appointment', a), ('photo', p)}
    assert [op for op, _, _ in adapter.log] == ['create', 'create']


def test_new_ancestors_without_question_cancels(store, adapter):
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    assert save_with_confirmation(store, adapter, [('photo', p)], SaveScope.SELF) is None


def test_delete_declined_cancels(store, adapter):
    store.delete('appointment', 12, parent_id=1)
    ask = Asker(False)
    assert save_with_confirmation(store, adapter, confirm_deletes=ask) is None
    assert ask.asked[0].deleted_branches == (('appointment', 12),)
    assert store.has_draft('appointment', 12)


def test_delete_accepted(store, adapter):
    store.delete('appointment', 12, parent_id=1)
    result = save_with_confirmation(store, adapter, confirm_deletes=Asker(True))
    assert result.deleted == (('appointment', 12),)


def test_no_questions_when_not_needed(store, adapter):
    store.modify('appointment', 12, {'c': 1}, parent_id=1)
    ask = Asker(False)
    result = save_with_confirmation(store, adapter, confirm_new_ancestors=ask, confirm_deletes=ask)
    assert result.updated == (('appointment', 12),) and ask.asked == []


def test_nothing_to_save(store, adapter):
    assert save_with_confirmation(store, adapter).id_map == {}


def test_drafts_changed_during_dialog_asks_again(store, adapter):
    """Пока был открыт диалог, добавилась удаляемая ветка — спросить снова."""
    store.delete('appointment', 12, parent_id=1)
    calls = []

    def ask(plan):
        calls.append(plan.deleted_branches)
        if len(calls) == 1:
            store.delete('appointment', 13, parent_id=1)       # изменение «во время диалога»
        return True

    result = save_with_confirmation(store, adapter, confirm_deletes=ask)
    assert calls == [(('appointment', 12),), (('appointment', 12), ('appointment', 13))]
    assert set(result.deleted) == {('appointment', 12), ('appointment', 13)}


# ---------------------------------------------------------------------------
# DraftsQtBridge
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge(store):
    b = DraftsQtBridge(store)
    got = {'status': [], 'remap': [], 'has': []}
    b.row_status_changed.connect(lambda e, i, s: got['status'].append((e, i, s)))
    b.row_remapped.connect(lambda e, o, n: got['remap'].append((e, o, n)))
    b.has_changes_changed.connect(got['has'].append)
    yield b, got
    b.detach()


def test_bridge_row_statuses_for_node_and_ancestors(store, bridge):
    b, got = bridge
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert got['status'] == [('photo', 7, 'own'), ('appointment', 12, 'child'), ('patient', 1, 'child')]
    assert got['has'] == [True]
    store.discard([('photo', 7)])
    assert got['status'][-3:] == [('photo', 7, None), ('appointment', 12, None), ('patient', 1, None)]
    assert got['has'] == [True, False]


def test_bridge_remap_after_save(store, adapter, bridge):
    from app.utils.drafts import build_plan, execute_plan
    b, got = bridge
    a = store.create('appointment', {}, parent_id=1)
    result = execute_plan(store, build_plan(store), adapter)
    assert got['remap'] == [('appointment', a, result.id_map[('appointment', a)])]


def test_bridge_detach(store, bridge):
    b, got = bridge
    b.detach()
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert got['status'] == []


def test_describe_nodes_for_dialogs(schema):
    from interfaces.gui.gui_window.drafts_qt import describe_nodes
    text = describe_nodes(schema, [('appointment', 12), ('photo', -1)])
    assert text == '• Приём №12\n• Фото (новая запись)'
    many = describe_nodes(schema, [('photo', i) for i in range(1, 21)], limit=3)
    assert many.splitlines()[-1] == '… и ещё 17'
