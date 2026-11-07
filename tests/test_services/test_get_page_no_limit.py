# tests/test_services/test_get_page_no_limit.py

"""get_page_filtered(limit=None) — «без предела», в том числе при нечётком поиске (ОСТ п. 5.14)."""

import pytest

from app.database.database import Database
from app.dto.dto_all import PatientDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.services.services_all import AppointmentService, NoteService, PatientService, PhotoService, _page_slice


@pytest.fixture
def patients(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    storage.mkdir()
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    service = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    for name in ('Иванов', 'Иванова', 'Иваненко', 'Петров'):
        service.create(PatientDTO(last_name=name, first_name='Иван'))
    yield service
    db.close()


FUZZY = [{'column': 'last_name', 'operator': 'fuzzy', 'value': 'Иванов'}]


def test_no_limit_returns_all(patients):
    items, total = patients.get_page_filtered(0, None)
    assert len(items) == total == 4


def test_no_limit_with_offset(patients):
    items, total = patients.get_page_filtered(1, None, order_by=['id'])
    assert total == 4 and len(items) == 3


def test_no_limit_with_fuzzy(patients):
    items, total = patients.get_page_filtered(0, None, FUZZY, fuzzy_threshold=60)
    assert total == len(items) and 'Иванов' in [p.last_name for p in items]
    assert 'Петров' not in [p.last_name for p in items]


def test_limit_with_fuzzy_still_cuts_page(patients):
    all_items, total = patients.get_page_filtered(0, None, FUZZY, fuzzy_threshold=60)
    page, page_total = patients.get_page_filtered(1, 1, FUZZY, fuzzy_threshold=60)
    assert page_total == total and [p.id for p in page] == [p.id for p in all_items[1:2]]


def test_exact_no_limit_with_fuzzy(patients):
    items, total = patients.get_page_filtered_exact(0, None, FUZZY, fuzzy_threshold=60)
    assert total == len(items) > 0


def test_exact_no_limit_without_fuzzy(patients):
    items, total = patients.get_page_filtered_exact(0, None)
    assert len(items) == total == 4


def test_page_slice():
    assert _page_slice([1, 2, 3], 1, None) == [2, 3]
    assert _page_slice([1, 2, 3], 1, 1) == [2]
    assert _page_slice([1, 2, 3], 5, None) == []
