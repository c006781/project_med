# tests/test_repositories_full.py

from datetime import date, time

from app.backend.repositories import (
    PatientRepository, AppointmentRepository,
    AppointmentNoteRepository, PhotoRepository
)
from app.models.bd.models import Patient, Appointment, AppointmentNote, Photo

import pytest

# ---------- PatientRepository (дополнительные тесты) ----------
def test_patient_repository_get_unique_values(patient_repo, db_session):
    """Проверка получения уникальных значений столбца."""
    # Добавим несколько пациентов с разными фамилиями
    patients = [
        Patient(first_name="A", last_name="Smith"),
        Patient(first_name="B", last_name="Johnson"),
        Patient(first_name="C", last_name="Smith"),
    ]
    db_session.add_all(patients)
    db_session.commit()
    unique_last_names = patient_repo.get_unique_values("last_name")
    assert set(unique_last_names) == {"Smith", "Johnson"}

def test_patient_repository_add_and_get(patient_repo, db_session):
    patient = Patient(first_name="Test", last_name="Testov")
    patient_repo.add(patient)
    db_session.commit()
    fetched = patient_repo.get_by_id(patient.id)
    assert fetched is not None
    assert fetched.first_name == "Test"

# def test_patient_repository_update(patient_repo, db_session, sample_patient):
#     sample_patient.first_name = "Updated"
#     patient_repo.update(sample_patient)
#     db_session.commit()
#     updated = patient_repo.get_by_id(sample_patient.id)
#     assert updated.first_name == "Updated"

def test_patient_repository_delete(patient_repo, db_session, sample_patient):
    patient_repo.delete(sample_patient)
    db_session.commit()
    assert patient_repo.get_by_id(sample_patient.id) is None

# ---------- AppointmentNoteRepository ----------
def test_note_repository_get_by_id(note_repo, sample_note):
    note = note_repo.get_by_id(sample_note.id)
    assert note is not None
    assert note.text == "Тестовая заметка"

def test_note_repository_add(note_repo, db_session):
    note = AppointmentNote(text="Новая заметка")
    note_repo.add(note)
    db_session.commit()
    assert note.id is not None
    assert note_repo.get_by_id(note.id).text == "Новая заметка"

# def test_note_repository_update(note_repo, db_session, sample_note):
#     sample_note.text = "Изменённая заметка"
#     note_repo.update(sample_note)
#     db_session.commit()
#     updated = note_repo.get_by_id(sample_note.id)
#     assert updated.text == "Изменённая заметка"

def test_note_repository_delete(note_repo, db_session, sample_note):
    note_repo.delete(sample_note)
    db_session.commit()
    assert note_repo.get_by_id(sample_note.id) is None

def test_note_repository_get_unique_values(note_repo, db_session):
    notes = [
        AppointmentNote(text="Текст A"),
        AppointmentNote(text="Текст B"),
        AppointmentNote(text="Текст A"),
    ]
    db_session.add_all(notes)
    db_session.commit()
    unique_texts = note_repo.get_unique_values("text")
    assert set(unique_texts) == {"Текст A", "Текст B"}

def test_note_repository_get_by_text_exact(note_repo, sample_note):
    note = note_repo.get_by_text_exact("Тестовая заметка")
    assert note is not None
    assert note.id == sample_note.id
    assert note_repo.get_by_text_exact("Несуществующий текст") is None

# ---------- AppointmentRepository ----------
def test_appointment_repository_get_by_id(appointment_repo, sample_appointment):
    app = appointment_repo.get_by_id(sample_appointment.id)
    assert app is not None
    assert app.patient_id == sample_appointment.patient_id

def test_appointment_repository_get_by_patient_with_relations(appointment_repo, sample_appointment, sample_patient, db_session):
    # Добавим ещё один приём для того же пациента
    from datetime import date, time
    app2 = Appointment(patient_id=sample_patient.id, date=date.today(), time=time(11, 0))
    db_session.add(app2)
    db_session.commit()
    apps = appointment_repo.get_by_patient_with_relations(sample_patient.id)
    assert len(apps) == 2
    assert sample_appointment.id in [a.id for a in apps]

def test_appointment_repository_add(appointment_repo, db_session, sample_patient):
    app = Appointment(patient_id=sample_patient.id, date=date.today())
    appointment_repo.add(app)
    db_session.commit()
    assert app.id is not None

# def test_appointment_repository_update(appointment_repo, db_session, sample_appointment):
#     sample_appointment.time = time(14, 30)
#     appointment_repo.update(sample_appointment)
#     db_session.commit()
#     updated = appointment_repo.get_by_id(sample_appointment.id)
#     assert updated.time == time(14, 30)

def test_appointment_repository_delete(appointment_repo, db_session, sample_appointment):
    appointment_repo.delete(sample_appointment)
    db_session.commit()
    assert appointment_repo.get_by_id(sample_appointment.id) is None

def test_appointment_repository_get_unique_values(appointment_repo, db_session, sample_patient):
    from datetime import date
    dates = [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 1)]
    for d in dates:
        app = Appointment(patient_id=sample_patient.id, date=d)
        db_session.add(app)
    db_session.commit()
    unique_dates = appointment_repo.get_unique_values("date")
    assert set(unique_dates) == {date(2025, 1, 1), date(2025, 1, 2)}

# ---------- PhotoRepository ----------
def test_photo_repository_get_by_appointment(photo_repo, sample_photo, sample_appointment, db_session):
    # Добавим ещё одно фото
    photo2 = Photo(appointment_id=sample_appointment.id, file_path="another.jpg")
    db_session.add(photo2)
    db_session.commit()
    photos = photo_repo.get_by_appointment(sample_appointment.id)
    assert len(photos) == 2
    assert sample_photo.id in [p.id for p in photos]

def test_photo_repository_get_by_id(photo_repo, sample_photo):
    photo = photo_repo.get_by_id(sample_photo.id)
    assert photo is not None
    assert photo.file_path == sample_photo.file_path

def test_photo_repository_add(photo_repo, db_session, sample_appointment):
    photo = Photo(appointment_id=sample_appointment.id, file_path="new.jpg")
    photo_repo.add(photo)
    db_session.commit()
    assert photo.id is not None

def test_photo_repository_delete(photo_repo, db_session, sample_photo):
    photo_repo.delete(sample_photo)
    db_session.commit()
    assert photo_repo.get_by_id(sample_photo.id) is None

def test_photo_repository_get_unique_values(photo_repo, db_session, sample_appointment):
    paths = ["path1.jpg", "path2.jpg", "path1.jpg"]
    for p in paths:
        photo = Photo(appointment_id=sample_appointment.id, file_path=p)
        db_session.add(photo)
    db_session.commit()
    unique_paths = photo_repo.get_unique_values("file_path")
    assert set(unique_paths) == {"path1.jpg", "path2.jpg"}