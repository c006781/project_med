# tests/test_drafts/test_qt_dialogs.py

"""
Диалоги сохранения ``app.utils.drafts_qt.dialogs``: ответы пользователя подменяются
(``QMessageBox``), проверяется, что функции возвращают и что показывают.
"""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.utils.drafts import build_plan  # noqa: E402
from app.utils.drafts_qt import dialogs  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def answer(monkeypatch):
    """Подмена статических вопросов QMessageBox: отвечает state['answer'], тексты — в state['texts']."""
    state = {'answer': QMessageBox.Yes, 'texts': []}

    def fake(parent, title, text, *args, **kwargs):
        state['texts'].append((title, text))
        return state['answer']

    monkeypatch.setattr(QMessageBox, 'question', staticmethod(fake))
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(fake))
    return state


@pytest.mark.parametrize('reply, expected', [
    (QMessageBox.Save, 'save'), (QMessageBox.Discard, 'discard'), (QMessageBox.Cancel, 'cancel'),
])
def test_ask_on_close(qapp, answer, reply, expected):
    answer['answer'] = reply
    assert dialogs.ask_on_close(None) == expected


def test_confirm_new_ancestors_text_and_answer(qapp, answer, store):
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    plan = build_plan(store, [('photo', p)])
    ask_new, _ = dialogs.make_confirmations(None, store.schema)
    assert ask_new(plan) is True
    assert 'Приём (новая запись)' in answer['texts'][-1][1]
    answer['answer'] = QMessageBox.No
    assert ask_new(plan) is False


def test_confirm_deletes_lists_lost_changes(qapp, answer, store):
    store.delete('appointment', 12, parent_id=1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    _, ask_delete = dialogs.make_confirmations(None, store.schema)
    assert ask_delete(build_plan(store)) is True
    text = answer['texts'][-1][1]
    assert 'Приём №12' in text and 'будут потеряны' in text and 'Фото №7' in text


@pytest.mark.parametrize('button, expected', [('Всё', 'all'), ('Текущее', 'current'), ('Отмена', None)])
def test_ask_save_target(qapp, monkeypatch, button, expected):
    clicked = {}

    def fake_exec(box):
        clicked['button'] = next(b for b in box.buttons() if b.text() == button)
        return 0

    monkeypatch.setattr(QMessageBox, 'exec', fake_exec)
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda box: clicked['button'])
    assert dialogs.ask_save_target(None) == expected


def test_ask_save_target_without_current(qapp, monkeypatch):
    seen = {}

    def fake_exec(box):
        seen['texts'] = [b.text() for b in box.buttons()]
        return 0

    monkeypatch.setattr(QMessageBox, 'exec', fake_exec)
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda box: None)
    assert dialogs.ask_save_target(None, has_current=False) is None
    assert 'Текущее' not in seen['texts']
