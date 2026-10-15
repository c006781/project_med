# tests/test_drafts/test_qt_page.py

"""
Страница ``app.utils.drafts_qt.DraftTablePage`` (offscreen Qt): две страницы
«приёмы → фото» на одном хранилище, источник строк в памяти.
"""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.utils.drafts import MISSING, SaveScope, build_plan, execute_plan  # noqa: E402
from app.utils.drafts_qt import Column, DraftTablePage  # noqa: E402


class ListSource:
    """Источник строк из списка; фильтр по полю родителя."""

    def __init__(self, rows, parent_field=None):
        self.rows = rows
        self.parent_field = parent_field
        self.calls = 0

    def load(self, offset, limit, parent_id):
        self.calls += 1
        rows = [r for r in self.rows
                if parent_id is MISSING or self.parent_field is None or r[self.parent_field] == parent_id]
        return [dict(r) for r in rows[offset:offset + limit]], len(rows)


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def frame(qapp, store):
    """Приёмы пациента 1 (3 шт., по 2 на странице) и фото выбранного приёма."""
    appointments_src = ListSource([{'id': i, 'patient_id': 1, 'cost': i * 100} for i in (12, 13, 14)],
                                  'patient_id')
    photos_src = ListSource([{'id': 7, 'appointment_id': 12, 'file_path': 'a.jpg'},
                             {'id': 8, 'appointment_id': 13, 'file_path': 'b.jpg'}], 'appointment_id')
    saved = []
    appointments = DraftTablePage(store, 'appointment', [Column('cost', 'Стоимость', from_edit=int)],
                                  appointments_src, save_handler=saved.append, page_size=2)
    photos = DraftTablePage(store, 'photo', [Column('file_path', 'Файл')], photos_src,
                            requires_parent=True, default_row=lambda: {'file_path': ''})
    appointments.current_changed.connect(photos.set_parent)
    appointments.set_parent(1)
    yield appointments, photos, saved
    appointments.model.detach()
    photos.model.detach()


def test_child_page_empty_without_parent(frame):
    appointments, photos, _ = frame
    assert photos.model.rowCount() == 0
    assert not photos.add_btn.isEnabled()
    assert photos.add_row() is None


def test_selecting_parent_loads_children(frame):
    appointments, photos, _ = frame
    appointments.select_id(12)
    assert photos.parent_id == 12 and photos.model.row_id(0) == 7
    appointments.select_id(13)
    assert photos.model.row_id(0) == 8


def test_owner_scenario_switch_rows_and_back(frame, store):
    """Изменили фото приёма 12 → приём 13, новое фото → назад к 12: всё на месте."""
    appointments, photos, _ = frame
    appointments.select_id(12)
    photos.model.setData(photos.model.index(0, 0), 'a2.jpg')
    appointments.select_id(13)
    new_id = photos.add_row()
    assert photos.current_id() == new_id
    appointments.select_id(12)
    assert photos.model.data(photos.model.index(0, 0)) == 'a2.jpg'
    appointments.select_id(13)
    assert photos.model.row_of(new_id) >= 0
    assert store.status('appointment', 12) == 'child' and store.status('appointment', 13) == 'child'


def test_paging(frame):
    appointments, _, _ = frame
    assert appointments.page_label.text() == 'стр. 1 из 2'
    assert appointments.next_btn.isEnabled() and not appointments.prev_btn.isEnabled()
    appointments.go_to_page(1)
    assert appointments.model.row_id(0) == 14
    appointments.go_to_page(5)
    assert appointments.page_label.text() == 'стр. 2 из 2'


def test_buttons_follow_selection(frame):
    appointments, _, _ = frame
    appointments.select_id(12)
    assert appointments.delete_btn.isEnabled() and not appointments.undelete_btn.isEnabled()
    assert not appointments.discard_btn.isEnabled()
    appointments.delete_selected()
    assert appointments.undelete_btn.isEnabled() and appointments.discard_btn.isEnabled()
    appointments.undelete_selected()
    assert not appointments.discard_btn.isEnabled()


def test_targets(frame):
    appointments, _, _ = frame
    appointments.select_id(13)
    assert appointments.current_node() == ('appointment', 13)
    assert appointments.selected_nodes() == [('appointment', 13)]
    assert appointments.page_nodes() == [('appointment', 12), ('appointment', 13)]


def test_save_button_calls_handler(frame):
    appointments, _, saved = frame
    appointments.save_btn.click()
    assert saved == [appointments]


def test_discard_branch_button(frame, store):
    appointments, photos, _ = frame
    appointments.select_id(12)
    photos.model.setData(photos.model.index(0, 0), 'zzz')
    appointments.model.setData(appointments.model.index(0, 0), 1)
    appointments.discard_selected(SaveScope.BRANCH)
    assert store.is_empty


def test_selection_kept_after_save_remap(frame, store, adapter):
    appointments, photos, _ = frame
    appointments.select_id(12)
    new_id = photos.add_row()
    result = execute_plan(store, build_plan(store), adapter)
    real = result.id_map[('photo', new_id)]
    photos.source.rows.append({'id': real, 'appointment_id': 12, 'file_path': ''})
    QCoreApplication.processEvents()                   # отложенное перечитывание
    assert photos.current_id() == real
