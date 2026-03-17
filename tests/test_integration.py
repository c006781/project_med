
from pathlib import Path
import pytest
from datetime import date, time
from app.services import PatientService, AppointmentService, NoteService, PhotoService
from app.exceptions import PatientNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, AppointmentNotFoundError
from app.database.database_shema.clinic import Appointment


def test_full_patient_appointment_photo_flow(
    patient_service, 
    appointment_service, 
    note_service, 
    photo_service, 
    db_session, 
    tmp_path
):
    """
    Тест на создание полного цикла приёма (пациент -> приём -> заметка -> фото).
    Проверяет, что всё создалось и затем удаляется.
    """
    from app.dto import PatientDTO
    # 1. Создаём пациента
    patient_dto = PatientDTO(id=None, first_name="Иван", last_name="Иванов", birth_date=None, phone="", email="")
    created_patient = patient_service.create_patient(patient_dto)
    patient_id = created_patient.id

    from app.dto import AppointmentDTO
    # 2. Создаём приём с заметкой
    app_dto = AppointmentDTO(id=None, patient_id=patient_id, date=date.today(), time=time(10,0), note_id=None)
    created_app = appointment_service.create_appointment(app_dto, note_text="Первичный осмотр")
    appointment_id = created_app.id
    note_id = created_app.note_id

    # 3. Добавляем фото к приёму
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"fake image")
    photo_dto = photo_service.add_photo_to_appointment(appointment_id, str(img_path), "Фото лица")
    photo_id = photo_dto.id

    # 4. Проверяем, что всё создалось
    assert patient_service.get_patient_by_id(patient_id) is not None
    assert appointment_service.get_appointment(appointment_id) is not None
    assert note_service.get_note(note_id) is not None
    assert photo_service.get_by_id(photo_id) is not None

    # 5. Удаляем приём
    appointment_service.delete_appointment(appointment_id)
    db_session.commit()

    # 6. Приём не должен существовать
    with pytest.raises(AppointmentNotFoundError): 
        appointment_service.get_appointment(appointment_id)

    # 7. Заметка должна быть удалена (так как на неё больше не ссылаются)
    with pytest.raises(AppointmentNoteNotFoundError):
        note_service.get_note(note_id)

    # 8. Фото должно быть удалено (каскадно)
    with pytest.raises(PhotoNotFoundError):
        photo_service.get_by_id(photo_id)

    # 9. Файл фото должен быть удалён с диска
    assert not (Path(photo_service._storage_path) / photo_dto.file_path).exists()

    # 10. Пациент остался
    assert patient_service.get_patient_by_id(patient_id) is not None

def test_note_shared_between_appointments(
    patient_service, 
    appointment_service, 
    note_service, 
    db_session
):
    """
    Тест на создание приёмов с общей заметкой.
    Создаём пациента, заметку и два приёма с этой заметкой.
    Затем удаляем каждый приём, проверяя, что заметка осталась после удаления первого приёма,
    а удалится после удаления второго приёма.
    """
    from app.dto import PatientDTO
    # Создаём пациента
    patient_dto = PatientDTO(
        id=None, 
        first_name="Пётр", 
        last_name="Петров",
        # birth_date=None, 
        # phone=None, 
        # email=None
    )
    patient = patient_service.create_patient(patient_dto)
    # Создаём заметку
    note_dto = note_service.create_note("Общая заметка")
    # Создаём два приёма с этой заметкой
    from app.dto import AppointmentDTO
    app1 = appointment_service.create_appointment(
        AppointmentDTO(id=None, patient_id=patient.id, date=date.today(), time=time(9,0), note_id=note_dto.id)
    )
    app2 = appointment_service.create_appointment(
        AppointmentDTO(id=None, patient_id=patient.id, date=date.today(), time=time(10,0), note_id=note_dto.id)
    )
    # Удаляем первый приём
    appointment_service.delete_appointment(app1.id)
    db_session.commit()
    # Заметка должна остаться
    assert note_service.get_note(note_dto.id) is not None
    # Удаляем второй приём
    appointment_service.delete_appointment(app2.id)
    db_session.commit()
    # Заметка должна удалиться
    with pytest.raises(AppointmentNoteNotFoundError):
        note_service.get_note(note_dto.id)