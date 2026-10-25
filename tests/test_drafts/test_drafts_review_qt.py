# tests/test_drafts/test_drafts_review_qt.py

"""
Таблицы Qt ``app.utils.drafts_qt`` — находки сверки модуля (М4, 2026-10-25): DR4–DR6.

Каждый тест падает на коде до исправления (журнал — ``app/utils/drafts_qt/IMPLEMENTATION.md``).
"""

import logging
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.utils.drafts import DraftStore, EntityType, TreeSchema  # noqa: E402
from app.utils.drafts_qt import Column, DraftsQtBridge, DraftTableModel, DraftTablePage  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def _photos(store, parent_id):
    """Модель фото приёма ``parent_id`` (колонка связи — редактируемая)."""
    model = DraftTableModel(store, 'photo', [Column('file_path', 'Файл'),
                                             Column('appointment_id', 'Приём')])
    model.set_rows([], parent_id=parent_id)
    return model


def _delete_now(obj) -> None:
    """Удалить QObject сейчас (как при закрытии окна)."""
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


# ---------------------------------------------------------------------------
# DR4: новая запись, перенесённая к другому родителю, переходит в его таблицу
# ---------------------------------------------------------------------------

def test_dr4_new_row_moves_to_table_of_new_parent(qapp, store):
    old, new = _photos(store, 12), _photos(store, 13)
    try:
        photo = old.add_row({'file_path': 'a.jpg'})
        assert (old.rowCount(), new.rowCount()) == (1, 0)
        assert old.setData(old.index(0, 1), 13)                # поле связи → приём 13
        assert store.parent_of('photo', photo) == ('appointment', 13)
        assert (old.rowCount(), new.rowCount()) == (0, 1)
        assert new.row_id(0) == photo and new.record(0)['file_path'] == 'a.jpg'
        assert new.record(0)['appointment_id'] == 13
    finally:
        old.detach()
        new.detach()


def test_dr4_undo_of_move_returns_row(qapp, store):
    old, new = _photos(store, 12), _photos(store, 13)
    try:
        old.add_row({'file_path': 'a.jpg'})
        old.setData(old.index(0, 1), 13)
        store.undo()
        assert (old.rowCount(), new.rowCount()) == (1, 0)
    finally:
        old.detach()
        new.detach()


# ---------------------------------------------------------------------------
# DR5: кнопки страницы следуют изменениям черновиков, а не только выделению
# ---------------------------------------------------------------------------

class _Source:
    """Одна строка пациента."""

    def load(self, offset, limit, parent_id):
        return [{'id': 1, 'name': 'Иванов'}], 1


def test_dr5_discard_button_enabled_after_cell_edit(qapp):
    store = DraftStore(TreeSchema([EntityType('patient', label='Пациент')]))
    page = DraftTablePage(store, 'patient', [Column('name', 'Фамилия')], _Source())
    try:
        page.reload()
        page.select_id(1)
        assert not page.discard_btn.isEnabled()
        assert page.model.setData(page.model.index(0, 0), 'Петров')
        assert page.discard_btn.isEnabled()                    # есть что отменить
        store.discard()                                        # отменили из другого места
        assert not page.discard_btn.isEnabled()
    finally:
        page.model.detach()


# ---------------------------------------------------------------------------
# DR6: удалённые модель / мост не остаются подписчиками хранилища
# ---------------------------------------------------------------------------

def test_dr6_deleted_page_model_unsubscribes(qapp, caplog):
    store = DraftStore(TreeSchema([EntityType('patient', label='Пациент')]))
    page = DraftTablePage(store, 'patient', [Column('name', 'Фамилия')], _Source())
    page.reload()
    assert len(store._listeners) == 1
    _delete_now(page)
    assert store._listeners == []
    with caplog.at_level(logging.ERROR):
        store.modify('patient', 1, {'name': 'Петров'})
    assert not [r for r in caplog.records if 'подписчика' in r.getMessage()]


def test_dr6_deleted_bridge_unsubscribes(qapp, store):
    bridge = DraftsQtBridge(store)
    assert len(store._listeners) == 1
    _delete_now(bridge)
    assert store._listeners == []


def test_dr6_explicit_detach_still_works(qapp, store):
    model = DraftTableModel(store, 'patient', [Column('name', 'Фамилия')])
    model.detach()
    model.detach()                                             # повторно — без ошибки
    assert store._listeners == []
    _delete_now(model)
    assert store._listeners == []
