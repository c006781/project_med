# tests/test_services/test_new_table_by_config.py

"""
Проверка замысла слоя данных: НОВАЯ таблица подключается описанием (модель + DTO +
field_configs), без своего кода в сервисе.

Таблица «Назначение» (Prescription) — ребёнок приёма, с полем-заметкой (инструкция) в общей
таблице заметок. Сервис — BaseService с минимумом обязательных «крючков».
"""

import datetime
from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Database
from app.database.database_shema.clinic import Base
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.repositories.repositories_all import BaseRepository
from app.services import AppointmentService, NoteService, PatientService, PhotoService
from app.services.services_all import BaseService


class Prescription(Base):
    """Назначение к приёму (только для теста)."""
    __tablename__ = 'test_prescriptions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    appointment_id = Column(Integer, ForeignKey('appointments.id'), nullable=False)
    dosage = Column(String(100), nullable=False)
    instruction_id = Column(Integer, ForeignKey('appointments_notes.id'), nullable=True)
    instruction_note = relationship('AppointmentNote', foreign_keys=[instruction_id])


class PrescriptionDTO(BaseModel):
    """DTO назначения."""
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    appointment_id: int
    dosage: str
    instruction_id: Optional[int] = None
    instruction_text: Optional[str] = None


PRESCRIPTION_CONFIG = {
    'id': {'title': 'ID', 'editable': False, 'hidden': True, 'updatable': False},
    'appointment_id': {'title': 'Приём', 'required': True},
    'dosage': {'title': 'Дозировка', 'required': True},
    'instruction_id': {'title': 'ID инструкции', 'hidden': True, 'updatable': False},
    'instruction_text': {
        'title': 'Инструкция', 'virtual': True, 'is_note': 'instruction_id',
        'source_attr': 'instruction_note',
        'compute': {'func': lambda note: note.text if note else None, 'args': ['instruction_note']},
    },
}


class PrescriptionRepository(BaseRepository):
    model_class = Prescription


class PrescriptionService(BaseService):
    """Только обязательные «крючки» — никакой логики сущности."""

    def __init__(self, db, note_service):
        super().__init__(db, PrescriptionRepository, Prescription, PrescriptionDTO, PRESCRIPTION_CONFIG)
        self._note_service = note_service

    def _get_note_service(self):
        return self._note_service

    def _not_found_exception(self, entity_id):
        return LookupError(f'назначение {entity_id} не найдено')


@pytest.fixture
def env(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    Base.metadata.create_all(db.engine)
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(tmp_path / 'ph'), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    rx = PrescriptionService(db, note)
    p = patient.create(PatientDTO(first_name='И', last_name='П', birth_date=datetime.date(1990, 1, 1)))
    a1 = appointment.create(AppointmentDTO(patient_id=p.id, date=datetime.date(2026, 1, 1)))
    a2 = appointment.create(AppointmentDTO(patient_id=p.id, date=datetime.date(2026, 1, 2)))
    yield {'db': db, 'rx': rx, 'note': note, 'appointment': appointment, 'a1': a1, 'a2': a2}
    db.close()


def test_create_read_with_note(env):
    rx = env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage='1 т.',
                                          instruction_text='после еды'))
    assert rx.id and rx.instruction_text == 'после еды'
    assert env['rx'].get_by_id(rx.id).instruction_text == 'после еды'


def test_required_and_parent_validation(env):
    with pytest.raises(ValueError):
        env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage=''))
    with pytest.raises(ValueError, match='appointments'):
        env['rx'].create(PrescriptionDTO(appointment_id=999, dosage='1'))


def test_page_sort_filter_by_note(env):
    for dosage, text in (('2', 'утром'), ('1', 'вечером'), ('3', 'днём')):
        env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage=dosage, instruction_text=text))
    items, total = env['rx'].get_page(0, 10, order_by=['instruction_text'])
    assert total == 3 and [i.instruction_text for i in items] == ['вечером', 'днём', 'утром']
    found, n = env['rx'].get_page(0, 10, filters=[{'column': 'instruction_text', 'operator': 'ilike', 'value': 'еч'}])
    assert n == 1 and found[0].dosage == '1'


def test_update_note_move_and_delete(env):
    rx = env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage='1', instruction_text='А'))
    updated = env['rx'].update(env['rx'].get_by_id(rx.id).model_copy(
        update={'instruction_text': 'Б', 'appointment_id': env['a2'].id}))
    assert updated.instruction_text == 'Б' and updated.appointment_id == env['a2'].id
    env['rx'].delete(rx.id)
    with pytest.raises(LookupError):
        env['rx'].get_by_id(rx.id)
    # заметки назначения удалены как неиспользуемые (ссылки на заметки — из схемы, DYN2)
    assert env['note'].get_unique_note_texts() == [] or 'Б' not in env['note'].get_unique_note_texts()


def test_new_table_note_protects_shared_note(env):
    """Заметка, используемая и приёмом, и назначением, не удаляется при удалении назначения."""
    appt = env['appointment'].update(env['appointment'].get_by_id(env['a1'].id).model_copy(
        update={'procedure_text': 'общая'}))
    rx = env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage='1', instruction_id=appt.procedure_id))
    env['rx'].delete(rx.id)
    assert env['note'].get_note(appt.procedure_id).text == 'общая'


def test_plain_base_service_without_subclass(env):
    """Предельный случай замысла: ни подкласса сервиса, ни репозитория — только описание."""
    from app.exceptions.exceptions_all import EntityNotFoundError
    rx = BaseService(env['db'], None, Prescription, PrescriptionDTO, PRESCRIPTION_CONFIG,
                     note_service=env['note'])
    created = rx.create(PrescriptionDTO(appointment_id=env['a1'].id, dosage='2', instruction_text='на ночь'))
    assert rx.get_by_id(created.id).instruction_text == 'на ночь'
    items, total = rx.get_page(0, 10, order_by=['-dosage'])
    assert total == 1
    rx.delete(created.id)
    with pytest.raises(EntityNotFoundError):
        rx.get_by_id(created.id)
