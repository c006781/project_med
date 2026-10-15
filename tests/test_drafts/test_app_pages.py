# tests/test_drafts/test_app_pages.py

"""
Экраны приложения на новых черновиках (``interfaces/gui/gui_window/pages/draft_pages.py``)
на настоящей SQLite во временной папке; ``app.dependencies`` подменены сервисами теста.
"""

import datetime
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app.dependencies as deps  # noqa: E402
from app.draft.integration import ServiceAdapter, build_app_schema, make_parent_resolver  # noqa: E402
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO  # noqa: E402
from app.dto.field_configs import APPOINTMENT_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG  # noqa: E402
from app.utils.drafts import MISSING, DraftStore, build_plan, execute_plan  # noqa: E402
from interfaces.gui.gui_window.pages.draft_pages import (  # noqa: E402
    AppointmentsPhotosDraftFrame, PatientsDraftPage, ServiceRowSource, _date_from_edit,
    columns_from_config,
)
from tests.test_drafts.test_integration_services import services  # noqa: E402,F401 — фикстура


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def app_env(qapp, services, monkeypatch):  # noqa: F811
    """Сервисы теста вместо app.dependencies + хранилище и адаптер как в приложении."""
    monkeypatch.setattr(deps, 'get_patient_service', lambda: services['patient'])
    monkeypatch.setattr(deps, 'get_appointment_service', lambda: services['appointment'])
    monkeypatch.setattr(deps, 'get_photo_service', lambda: services['photo'])
    adapter = ServiceAdapter({
        'patient': (lambda: services['patient'], PatientDTO),
        'appointment': (lambda: services['appointment'], AppointmentDTO),
        'photo': (lambda: services['photo'], PhotoDTO),
    })
    schema = build_app_schema()
    store = DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter))
    patient = services['patient'].create(PatientDTO(first_name='Иван', last_name='Петров',
                                                    birth_date=datetime.date(1980, 5, 5)))
    other = services['patient'].create(PatientDTO(first_name='Анна', last_name='Сидорова',
                                                  birth_date=datetime.date(1990, 1, 1)))
    a1 = services['appointment'].create(AppointmentDTO(patient_id=patient.id, date=datetime.date(2026, 1, 1)))
    services['appointment'].create(AppointmentDTO(patient_id=other.id, date=datetime.date(2026, 2, 2)))
    return {**services, 'store': store, 'adapter': adapter, 'p': patient, 'other': other, 'a1': a1}


def test_columns_from_config():
    patient_fields = [c.field for c in columns_from_config(PATIENT_CONFIG)]
    assert patient_fields[:5] == ['last_name', 'first_name', 'middle_name', 'birth_date', 'phone']
    assert 'id' not in patient_fields and 'description_id' not in patient_fields
    appointment = {c.field: c for c in columns_from_config(APPOINTMENT_CONFIG, exclude=('patient_id',))}
    assert 'photos' not in appointment and 'patient_id' not in appointment
    assert not appointment['has_photos'].editable and not appointment['patient_name'].editable
    assert appointment['reason_text'].editable                     # заметка — редактируемая
    assert appointment['date'].text(datetime.date(2026, 10, 16)) == '16.10.2026'
    assert [c.field for c in columns_from_config(PHOTO_CONFIG)] == ['file_path', 'description']


@pytest.mark.parametrize('value, expected', [
    (QDate(2026, 10, 16), datetime.date(2026, 10, 16)),
    ('16.10.2026', datetime.date(2026, 10, 16)),
    ('2026-10-16', datetime.date(2026, 10, 16)),
    ('', None),
])
def test_date_from_edit(value, expected):
    assert _date_from_edit(value) == expected


def test_service_row_source_filters_by_parent(app_env):
    source = ServiceRowSource(lambda: app_env['appointment'], 'patient_id')
    rows, total = source.load(0, 50, app_env['p'].id)
    assert total == 1 and rows[0]['id'] == app_env['a1'].id
    rows, total = source.load(0, 50, MISSING)
    assert total == 2


def test_patients_page_opens_appointments(app_env):
    page = PatientsDraftPage(app_env['store'])
    page.on_enter()
    opened = []
    page.action_requested.connect(lambda obj: opened.append(obj.id))
    page.table.select_id(app_env['p'].id)
    page.appointments_btn.click()
    assert opened == [app_env['p'].id]
    page.table.model.detach()


def test_frame_new_appointment_with_photo_saved_together(app_env, tmp_path):
    """Фрейм: новый приём пациента + фото + правка пациента на «первом экране» — одно сохранение."""
    store = app_env['store']
    patients = PatientsDraftPage(store)
    patients.on_enter()
    patients.table.select_id(app_env['p'].id)
    row = patients.table.model.row_of(app_env['p'].id)
    patients.table.model.setData(patients.table.model.index(row, 2), 'Петрович')   # отчество

    frame = AppointmentsPhotosDraftFrame(store)
    frame.on_enter({'patient_id': app_env['p'].id})
    assert frame.appointments.model.rowCount() == 1
    new_app = frame.appointments.add_row()
    assert frame.photos.parent_id == new_app                 # новый приём стал текущим
    image = tmp_path / 'p.jpg'
    image.write_bytes(b'\xff\xd8fake')
    new_photo = frame.photos.add_row()
    col = [c.field for c in frame.photos.model.columns].index('file_path')
    frame.photos.model.setData(frame.photos.model.index(frame.photos.model.row_of(new_photo), col), str(image))
    assert store.status('patient', app_env['p'].id) == 'both'

    result = execute_plan(store, build_plan(store), app_env['adapter'])
    QCoreApplication.processEvents()
    real_app = result.id_map[('appointment', new_app)]
    assert app_env['photo'].get_all()[0].appointment_id == real_app
    assert app_env['patient'].get_by_id(app_env['p'].id).middle_name == 'Петрович'
    assert frame.appointments.model.rowCount() == 2          # перечитано из БД
    for page in (patients.table, frame.appointments, frame.photos):
        page.model.detach()


def test_b2_empty_filtered_page_does_not_crash(app_env):
    """B2: страница приёмов без результатов (новый пациент) — пусто, а не IndexError."""
    rows, total = ServiceRowSource(lambda: app_env['appointment'], 'patient_id').load(0, 50, -1)
    assert (rows, total) == ([], 0)
