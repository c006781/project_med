# tests/test_drafts/test_qt_model.py

"""
Модель таблицы ``app.utils.drafts_qt.DraftTableModel`` (offscreen Qt, без окна).

Две модели на одном хранилище имитируют две таблицы фрейма «Приёмы и фото».
"""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.utils.drafts import SaveScope, build_plan, execute_plan  # noqa: E402
from app.utils.drafts_qt import Column, DraftTableModel, StatusRole  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def appointments(qapp, store):
    model = DraftTableModel(store, 'appointment', [Column('cost', 'Стоимость', from_edit=int),
                                                  Column('date', 'Дата', editable=False)])
    model.set_rows([{'id': 12, 'patient_id': 1, 'cost': 400, 'date': 'd1'},
                    {'id': 13, 'patient_id': 1, 'cost': 500, 'date': 'd2'}], parent_id=1)
    yield model
    model.detach()


@pytest.fixture
def photos(qapp, store):
    model = DraftTableModel(store, 'photo', [Column('file_path', 'Файл')])
    model.set_rows([{'id': 7, 'appointment_id': 12, 'file_path': 'a.jpg'}], parent_id=12)
    yield model
    model.detach()


def cell(model, row, col, role=Qt.DisplayRole):
    return model.data(model.index(row, col), role)


def test_edit_creates_draft_and_revert_removes_it(appointments, store):
    assert appointments.setData(appointments.index(0, 0), '450')
    assert store.get('appointment', 12).data == {'cost': 450}
    assert cell(appointments, 0, 0) == '450' and cell(appointments, 0, 0, StatusRole) == 'own'
    appointments.setData(appointments.index(0, 0), 400)
    assert not store.has_draft('appointment', 12)
    assert cell(appointments, 0, 0, StatusRole) is None


def test_bad_value_rejected_and_readonly_column(appointments, store):
    assert not appointments.setData(appointments.index(0, 0), 'abc')
    assert not appointments.setData(appointments.index(0, 1), 'x')
    assert store.is_empty


def test_child_edit_in_other_table_marks_parent_row(appointments, photos, store):
    """Изменение фото во второй таблице → значок приёма в первой (родители из set_rows)."""
    changed = []
    appointments.dataChanged.connect(lambda a, b: changed.append(a.row()))
    photos.setData(photos.index(0, 0), 'b.jpg')
    assert cell(appointments, 0, 0, StatusRole) == 'child'
    assert 0 in changed
    assert store.status('patient', 1) == 'child'


def test_new_row_appears_in_matching_table_only(appointments, photos, store):
    new_id = photos.add_row({'file_path': 'n.jpg'})
    assert photos.rowCount() == 2 and photos.row_id(1) == new_id
    assert photos.is_new_row(1) and cell(photos, 1, 0, StatusRole) == 'new'
    other = store.create('photo', {'file_path': 'x'}, parent_id=13)      # другой приём
    assert photos.row_of(other) == -1


def test_reload_shows_new_drafts_of_context(qapp, store, photos):
    new_id = photos.add_row({'file_path': 'n.jpg'})
    photos.set_rows([{'id': 7, 'appointment_id': 12, 'file_path': 'a.jpg'}], parent_id=12)
    assert photos.row_of(new_id) == 1
    photos.set_rows([], parent_id=13)                       # перешли на другой приём
    assert photos.rowCount() == 0
    photos.set_rows([{'id': 7, 'appointment_id': 12, 'file_path': 'a.jpg'}], parent_id=12)
    assert photos.row_of(new_id) == 1                       # вернулись — черновик на месте


def test_discard_new_row_removes_it(photos, store):
    new_id = photos.add_row({'file_path': 'n.jpg'})
    photos.discard_rows([photos.row_of(new_id)])
    assert photos.rowCount() == 1


def test_delete_and_undelete(photos, store):
    photos.delete_rows([0])
    assert cell(photos, 0, 0, StatusRole) == 'deleted'
    assert cell(photos, 0, 0, Qt.FontRole).strikeOut()
    assert not (photos.flags(photos.index(0, 0)) & Qt.ItemIsEditable)
    photos.undelete_rows([0])
    assert cell(photos, 0, 0, StatusRole) is None


def test_discard_branch_from_parent_table(appointments, photos, store):
    photos.setData(photos.index(0, 0), 'b.jpg')
    appointments.setData(appointments.index(0, 0), 999)
    appointments.discard_rows([0], SaveScope.BRANCH)
    assert store.is_empty
    assert cell(photos, 0, 0) == 'a.jpg'


def test_save_remaps_id_and_requests_one_reload(photos, store, adapter):
    reloads, remaps = [], []
    photos.reload_requested.connect(lambda: reloads.append(1))
    photos.row_id_changed.connect(lambda old, new: remaps.append((old, new)))
    new_id = photos.add_row({'file_path': 'n.jpg'})
    photos.setData(photos.index(0, 0), 'b.jpg')
    result = execute_plan(store, build_plan(store), adapter)
    real = result.id_map[('photo', new_id)]
    assert remaps == [(new_id, real)] and photos.row_id(1) == real
    QCoreApplication.processEvents()
    assert reloads == [1]                     # одна просьба на всё сохранение


def test_headers_and_colors(appointments):
    assert appointments.headerData(0, Qt.Horizontal) == 'Стоимость'
    appointments.setData(appointments.index(0, 0), 1)
    assert cell(appointments, 0, 0, Qt.BackgroundRole) is not None
    assert cell(appointments, 1, 0, Qt.BackgroundRole) is None


def test_q1_undo_redo_new_row(photos, store):
    """Q1: отмена создания убирает строку, повтор возвращает; правка новой — откатывается."""
    new_id = photos.add_row({'file_path': 'n.jpg'})
    assert photos.rowCount() == 2
    store.undo()
    assert photos.rowCount() == 1 and photos.row_of(new_id) == -1
    store.redo()
    assert photos.row_of(new_id) == 1
    photos.setData(photos.index(1, 0), 'm.jpg')
    store.undo()
    assert photos.data(photos.index(1, 0)) == 'n.jpg'


def test_undo_existing_row_edit_refreshes(photos, store):
    photos.setData(photos.index(0, 0), 'b.jpg')
    store.undo()
    assert photos.data(photos.index(0, 0)) == 'a.jpg'
    assert photos.row_status(0) is None


def test_q2_no_data_changed_inside_reset(qapp, store):
    """Q2: связи сообщаются после сброса модели — dataChanged не посреди reset."""
    model = DraftTableModel(store, 'appointment', [Column('cost', 'Стоимость')])
    store.modify('photo', 7, {'a': 1}, parent_id=12)          # черновик в ветке приёма 12
    log, state = [], {'resetting': False}
    model.modelAboutToBeReset.connect(lambda: state.update(resetting=True))
    model.modelReset.connect(lambda: state.update(resetting=False))
    model.dataChanged.connect(lambda a, b: log.append(state['resetting']))
    model.set_rows([{'id': 12, 'patient_id': 1, 'cost': 1}], parent_id=1)
    assert log and not any(log)                               # были, но не во время сброса
    assert store.status('patient', 1) == 'child'
    model.detach()
