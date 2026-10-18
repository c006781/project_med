# tests/test_dataset_app/conftest.py

"""
Общие фикстуры тестов наборов данных в приложении: сервисы на настоящей SQLite во
временной папке, поставщики сервисов, данные, черновики приложения.
"""

import datetime

import pytest

from app.database import Database
from app.draft.integration import AppDrafts, ServiceAdapter, build_app_schema, make_parent_resolver
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.services import AppointmentService, NoteService, PatientService, PhotoService
from app.utils.drafts import DraftStore


@pytest.fixture
def services(tmp_path):
    """Сервисы на файле SQLite — как в app/dependencies.py (с конфигурациями полей)."""
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    storage.mkdir()
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    yield {'patient': patient, 'appointment': appointment, 'photo': photo, 'db': db}
    db.close()


@pytest.fixture
def providers(services):
    return {k: (lambda s=s: s) for k, s in services.items() if k != 'db'}


@pytest.fixture
def filled(services):
    """Два пациента; у первого — два приёма (один с заметкой), у второго — один."""
    p, a = services['patient'], services['appointment']
    ivanov = p.create(PatientDTO(last_name='Иванов', first_name='Иван', birth_date=datetime.date(1980, 1, 1)))
    petrov = p.create(PatientDTO(last_name='Петров', first_name='Пётр', birth_date=datetime.date(1990, 2, 2)))
    a.create(AppointmentDTO(patient_id=ivanov.id, date=datetime.date(2026, 1, 10), reason_text='боль'))
    a.create(AppointmentDTO(patient_id=ivanov.id, date=datetime.date(2026, 3, 5)))
    a.create(AppointmentDTO(patient_id=petrov.id, date=datetime.date(2026, 2, 1)))
    return {'ivanov': ivanov.id, 'petrov': petrov.id}


@pytest.fixture
def app_drafts(services, providers):
    adapter = ServiceAdapter({
        'patient': (providers['patient'], PatientDTO),
        'appointment': (providers['appointment'], AppointmentDTO),
        'photo': (providers['photo'], PhotoDTO),
    }, transaction_factory=lambda: services['db'].session_scope())
    schema = build_app_schema()
    store = DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter))
    return AppDrafts(schema=schema, adapter=adapter, store=store)
