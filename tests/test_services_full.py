# tests/test_services_full.py

from datetime import date, time
from app.dto import AppointmentDTO, AppointmentNoteDTO
from app.exceptions import AppointmentNotFoundError, PatientNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError
from pathlib import Path
import pytest

# ---------- AppointmentService ----------
def test_appointment_service_get_all(appointment_service, sample_appointment):
    apps = appointment_service.get_all()
    assert len(apps) >= 1
    assert any(a.id == sample_appointment.id for a in apps)

def test_appointment_service_get_by_id(appointment_service, sample_appointment):
    app = appointment_service.get_appointment(sample_appointment.id)
    assert app.id == sample_appointment.id

def test_appointment_service_get_by_id_not_found(appointment_service):
    with pytest.raises(AppointmentNotFoundError):
        appointment_service.get_appointment(9999)

def test_appointment_service_get_by_patient(appointment_service, sample_appointment, sample_patient, db_session):
    # Добавим ещё приём
    from app.database.database_shema.clinic import Appointment
    app2 = Appointment(patient_id=sample_patient.id, date=date.today())
    db_session.add(app2)
    db_session.commit()
    apps = appointment_service.get_appointments_by_patient(sample_patient.id)
    assert len(apps) == 2

def test_appointment_service_create(appointment_service, sample_patient, db_session):
    """
    Проверяет создание приёма с новой заметкой.
    """
    # from datetime import date, time
    from app.services import NoteService
    
    dto_in = AppointmentDTO(
        id=None,
        patient_id=sample_patient.id,
        date=date.today(),
        time=time(9, 0),
        note_id=None

    )
    

    dto_out = appointment_service.create_appointment(dto_in, note_text="Новая заметка")

    # assert dto_out.id is not None
    # assert dto_out.patient_id == sample_patient.id
    
    # assert dto_out.note_id is not None
    # note_service = appointment_service._note_service  # если есть доступ, но лучше через отдельный сервис
    # # Для проверки получим заметку через NoteService
    # from app.services import NoteService
    # note_svc = NoteService(appointment_service._db)
    # note = note_svc.get_note(dto_out.note_id)
    # assert note.text == "Новая заметка"



    # Проверяем, что приём создан и получил ID
    assert dto_out.id is not None
    assert dto_out.patient_id == sample_patient.id
    assert dto_out.note_id is not None # Проверим, что заметка создалась

    # Проверяем, что заметка действительно создалась и имеет правильный текст
    note_service = NoteService(appointment_service._db)
    note = note_service.get_note(dto_out.note_id)
    assert note.text == "Новая заметка"
    assert note.id == dto_out.note_id


# def test_appointment_service_create(appointment_service, sample_patient, db_session):
#     from app.services import NoteService
#     note_service = NoteService(appointment_service._db)
#     # ...
#     dto_out = appointment_service.create_appointment(dto_in, note_text="Новая заметка")
#     assert dto_out.note_id is not None
#     note = note_service.get_note(dto_out.note_id)
#     assert note.text == "Новая заметка"



def test_appointment_service_create_with_existing_note(appointment_service, sample_patient, sample_note):
    """
    Проверяет создание приёма с уже существующей заметкой (note_id передан в DTO).
    """
    from datetime import date, time
    from app.services import NoteService

    dto_in = AppointmentDTO(
        id=None,
        patient_id=sample_patient.id,
        date=date.today(),
        time=time(9, 0),
        note_id=sample_note.id # передаём ID существующей заметки
    )
    dto_out = appointment_service.create_appointment(dto_in) # note_text не передаём

    # Проверяем, что приём привязан к переданной заметке
    assert dto_out.note_id == sample_note.id

    # Дополнительно убедимся, что текст заметки не изменился
    note_service = NoteService(appointment_service._db)
    note = note_service.get_note(dto_out.note_id)
    assert note.text == sample_note.text

def test_appointment_service_create_patient_not_found(appointment_service):
    dto_in = AppointmentDTO(
        id=None,
        patient_id=9999,
        date=date.today(),
        time=time(9, 0),
        note_id=None
    )
    with pytest.raises(PatientNotFoundError):
        appointment_service.create_appointment(dto_in)

def test_appointment_service_update(appointment_service, sample_appointment):
    dto_update = AppointmentDTO(
        id=sample_appointment.id,
        patient_id=sample_appointment.patient_id,
        date=date(2025, 12, 31),
        time=time(18, 0),
        note_id=None
    )
    updated = appointment_service.update_appointment(dto_update)
    assert updated.date == date(2025, 12, 31)
    assert updated.time == time(18, 0)

def test_appointment_service_update_with_new_note(appointment_service, sample_appointment):
    updated = appointment_service.update_appointment(
        AppointmentDTO.from_orm(sample_appointment),
        note_text="Обновлённая заметка"
    )
    assert updated.note_id is not None
    # Проверим, что старая заметка не удалена (если была)
    if sample_appointment.note_id:
        old_note = sample_appointment.note_id
        # Должна остаться в БД? По логике, если создаётся новая заметка, старая остаётся, если на неё никто не ссылается.
        # Но в текущей реализации update_appointment создаёт новую заметку и подменяет note_id, старая не удаляется автоматически.
        # Это может быть особенностью. В тесте можно проверить, что новая заметка создалась.
        from app.services import NoteService
        note_svc = NoteService(appointment_service._db)
        new_note = note_svc.get_note(updated.note_id)
        assert new_note.text == "Обновлённая заметка"

def test_appointment_service_delete(appointment_service, sample_appointment, db_session):
    appointment_service.delete_appointment(sample_appointment.id)
    db_session.commit()
    with pytest.raises(AppointmentNotFoundError):
        appointment_service.get_appointment(sample_appointment.id)

def test_appointment_service_delete_with_note_cleanup(appointment_service, sample_appointment, db_session):
    """При удалении последнего приёма, ссылающегося на заметку, заметка должна удалиться."""
    note_id = sample_appointment.note_id
    appointment_service.delete_appointment(sample_appointment.id)
    db_session.commit()
    # Проверим, что заметка удалена
    from app.services import NoteService
    note_svc = NoteService(appointment_service._db)
    with pytest.raises(AppointmentNoteNotFoundError):
        note_svc.get_note(note_id)

# ---------- NoteService ----------
def test_note_service_get_all(note_service, sample_note):
    notes = note_service.get_all()
    assert len(notes) >= 1
    assert any(n.id == sample_note.id for n in notes)

def test_note_service_get_note(note_service, sample_note):
    note = note_service.get_note(sample_note.id)
    assert note.id == sample_note.id

def test_note_service_get_note_not_found(note_service):
    with pytest.raises(AppointmentNoteNotFoundError):
        note_service.get_note(9999)

def test_note_service_create_note(note_service):
    dto = note_service.create_note("Созданная заметка")
    assert dto.id is not None
    assert dto.text == "Созданная заметка"

def test_note_service_update_note(note_service, sample_note):
    updated = note_service.update_note(sample_note.id, "Обновлённый текст")
    assert updated.text == "Обновлённый текст"

def test_note_service_delete_note(note_service, sample_note, db_session):
    note_service.delete_note(sample_note.id)
    db_session.commit()
    with pytest.raises(AppointmentNoteNotFoundError):
        note_service.get_note(sample_note.id)

def test_note_service_get_or_create_note_existing(note_service, sample_note):
    dto = note_service.get_or_create_note(sample_note.text)
    assert dto.id == sample_note.id

def test_note_service_get_or_create_note_new(note_service):
    dto = note_service.get_or_create_note("Абсолютно новый текст")
    assert dto.id is not None
    # Проверим, что можно получить по тексту
    dto2 = note_service.get_or_create_note("Абсолютно новый текст")
    assert dto2.id == dto.id  # должен вернуть ту же

def test_note_service_get_or_create_note_empty(note_service):
    assert note_service.get_or_create_note("") is None
    assert note_service.get_or_create_note(None) is None

# ---------- PhotoService (дополнительные тесты) ----------
def test_photo_service_get_all(photo_service, sample_photo):
    photos = photo_service.get_all()
    assert len(photos) >= 1
    assert any(p.id == sample_photo.id for p in photos)

def test_photo_service_get_photos_for_appointment(photo_service, sample_photo, sample_appointment):
    photos = photo_service.get_photos_for_appointment(sample_appointment.id)
    assert len(photos) == 1
    assert photos[0].id == sample_photo.id

def test_photo_service_get_by_id(photo_service, sample_photo):
    photo = photo_service.get_by_id(sample_photo.id)
    assert photo.id == sample_photo.id

def test_photo_service_delete_photo(photo_service, sample_photo, tmp_path, db_session):
    # Убедимся, что файл существует
    # full_path = photo_service._storage_path / sample_photo.file_path
    # full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path = Path(photo_service._storage_path) / sample_photo.file_path   # <-- исправлено
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"dummy")
    photo_service.delete_photo(sample_photo.id)
    db_session.commit()
    with pytest.raises(PhotoNotFoundError):
        photo_service.get_by_id(sample_photo.id)
    assert not full_path.exists()

# ---------- SyncService (без Qt) ----------
def test_sync_service_prepare_download(sync_service):
    thread = sync_service.prepare_download()
    assert thread.token == sync_service.token
    assert thread.remote_path == sync_service.remote_path
    assert thread.local_path == sync_service.local_path

def test_sync_service_prepare_upload(sync_service):
    thread = sync_service.prepare_upload()
    assert thread.token == sync_service.token
    assert thread.local_path == sync_service.local_path
    assert thread.remote_path == sync_service.remote_path