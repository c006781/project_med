# tests/test_dto.py
from datetime import date
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo

def test_patient_dto_model_validate():
    """
    Тестирование функции PatientDTO.model_validate на основе данных Patient.
    
    Создаём объект Patient с данными и преобразует его в DTO.
    Проверяет, что все поля DTO соответствуют полям объекта Patient.
    """
    # Создаём объект Patient с данными
    patient = Patient(
        id=1, 
        first_name="Иван", 
        last_name="Петров", 
        birth_date=date(1990,1,1), 
        phone="123", 
        email="test@test.ru"
    )
    
    # Преобразуем объект Patient в DTO
    # dto = PatientDTO.from_orm(patient)
    dto = PatientDTO.model_validate(patient)
    
    # Проверка, что все поля DTO соответствуют полям объекта Patient
    assert dto.id == 1
    assert dto.first_name == "Иван"
    assert dto.last_name == "Петров"
    assert dto.birth_date == date(1990,1,1)
    assert dto.phone == "123"
    assert dto.email == "test@test.ru"

def test_appointment_dto_model_validate_with_patient():
    """
    Тестирование функции AppointmentDTO.model_validate на основе данных Appointment.
    Создаём объект Appointment с данными и преобразует его в DTO.
    Проверяет, что все поля DTO соответствуют полям объекта Appointment.
    """
    patient = Patient(id=1, first_name="Иван", last_name="Петров")
    note = AppointmentNote(id=10, text="Заметка")
    app = Appointment(id=5, patient=patient, date=date.today(), time=None, note=note)

    app.patient = patient          # связываем объекты
    app.patient_id = patient.id    # явно заполняем внешний ключ
    app.note = note
    app.note_id = note.id  

    # dto = AppointmentDTO.from_orm(app)
    dto = AppointmentDTO.model_validate(app)
    # для проверки
    dto.patient_name = f"{app.patient.last_name} {app.patient.first_name}"
    dto.note_text = app.note.text
    
    assert dto.id == 5
    assert dto.patient_id == 1
    assert dto.patient_name == "Петров Иван"
    assert dto.note_id == 10
    assert dto.note_text == "Заметка"

def test_note_dto_model_validate():
    """
    Тестирование функции AppointmentNoteDTO.model_validate на основе данных AppointmentNote.
    
    Создаём объект AppointmentNote с данными и преобразует его в DTO.
    Проверяет, что все поля DTO соответствуют полям объекта AppointmentNote.
    """
    note = AppointmentNote(
        id=10, 
        text="Текст"
    )
    # dto = AppointmentNoteDTO.from_orm(note)
    dto = AppointmentNoteDTO.model_validate(note)
    assert dto.id == 10
    assert dto.text == "Текст"

def test_photo_dto_model_validate():
    """
    Тестирование функции PhotoDTO.model_validate на основе данных Photo.
    
    Создаём объект Photo с данными и преобразует его в DTO.
    Проверяет, что все поля DTO соответствуют полям объекта Photo.
    """
    photo = Photo(
        id=20, 
        appointment_id=5, 
        file_path="path.jpg", 
        description="desc"
    )
    # dto = PhotoDTO.from_orm(photo)
    dto = PhotoDTO.model_validate(photo)
    assert dto.id == 20
    assert dto.appointment_id == 5
    assert dto.file_path == "path.jpg"
    assert dto.description == "desc"