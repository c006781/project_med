import pytest
from datetime import date
from app.services import PatientService, AppointmentService, NoteService
from app.exceptions import PatientNotFoundError, AppointmentNoteNotFoundError
from app.database.database_shema.clinic import Appointment

def test_patient_delete_cascade(patient_service, db_session, sample_patient, sample_note):
    """
    Проверяет удаление приёма и заметки при удалении пациента.

    Создаём приём, связанный с заметкой, удаляем пациента, а затем
    проверяем, что приём и заметка не существуют.
    """
    # Создаём приём, связанный с заметкой
    app = Appointment(
        patient_id=sample_patient.id,
        date=date.today(),
        note_id=sample_note.id
    )
    db_session.add(app)
    db_session.commit()
    note_id = sample_note.id

    # Удаляем пациента
    patient_service.delete_patient(sample_patient.id)
    db_session.commit()

    # Пациент не должен существовать
    with pytest.raises(PatientNotFoundError):
        patient_service.get_patient_by_id(sample_patient.id)

    # Приём должен быть удалён каскадно
    from app.repositories import AppointmentRepository
    repo = AppointmentRepository(db_session)
    assert repo.get_by_id(app.id) is None

    # Заметка должна быть удалена, так как больше не используется
    note_svc = NoteService(patient_service._db)
    with pytest.raises(AppointmentNoteNotFoundError):
        note_svc.get_note(note_id)

def test_appointment_update_replace_note(appointment_service, db_session, sample_appointment):
    """
    Проверяет обновление приёма с заменой заметки.

    Создаём приём, связанный с заметкой, обновляем приём, передавая новый текст
    заметки, и проверяем, что старая заметка удаляется, если на неё никто не ссылается.
    """
    old_note_id = sample_appointment.note_id
    # Обновляем приём, передавая новый текст заметки
    updated = appointment_service.update_appointment(
        appointment_service.get_appointment(sample_appointment.id),
        note_text="Совершенно новая заметка"
    )
    assert updated.note_id is not None
    assert updated.note_id != old_note_id

    # Принудительно фиксируем изменения и сбрасываем кеш сессии
    db_session.commit()
    db_session.expire_all()

    # Старая заметка должна быть удалена (если на неё никто не ссылается)
    note_svc = appointment_service._note_service
    with pytest.raises(AppointmentNoteNotFoundError):
        note_svc.get_note(old_note_id)

def test_two_appointments_same_note(appointment_service, note_service, db_session, sample_patient):
    """
    Проверяет, что при удалении одного из двух приёмов, ссылающихся на одну заметку,
    заметка остаётся, а при удалении второго приёма, заметка удаляется.
    """
    # Создаём заметку
    note_dto = note_service.create_note("Общая заметка")
    # Создаём два приёма с этой заметкой
    from app.dto import AppointmentDTO
    from datetime import date, time
    app1 = appointment_service.create_appointment(
        AppointmentDTO(id=None, patient_id=sample_patient.id, date=date.today(), time=time(10,0), note_id=note_dto.id)
    )
    app2 = appointment_service.create_appointment(
        AppointmentDTO(id=None, patient_id=sample_patient.id, date=date.today(), time=time(11,0), note_id=note_dto.id)
    )

    # Удаляем один приём
    appointment_service.delete_appointment(app1.id)
    db_session.commit()

    # Заметка должна остаться
    note = note_service.get_note(note_dto.id)
    assert note.id == note_dto.id

    # Удаляем второй приём
    appointment_service.delete_appointment(app2.id)
    db_session.commit()

    # Заметка должна удалиться
    with pytest.raises(AppointmentNoteNotFoundError):
        note_service.get_note(note_dto.id)