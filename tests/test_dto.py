# tests/test_dto.py
from datetime import date
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo

def test_patient_dto_from_orm():
    patient = Patient(id=1, first_name="Иван", last_name="Петров", birth_date=date(1990,1,1), phone="123", email="test@test.ru")
    dto = PatientDTO.from_orm(patient)
    assert dto.id == 1
    assert dto.first_name == "Иван"
    assert dto.last_name == "Петров"
    assert dto.birth_date == date(1990,1,1)
    assert dto.phone == "123"
    assert dto.email == "test@test.ru"

def test_appointment_dto_from_orm_with_patient():
    patient = Patient(id=1, first_name="Иван", last_name="Петров")
    note = AppointmentNote(id=10, text="Заметка")
    app = Appointment(id=5, patient=patient, date=date.today(), time=None, note=note)

    app.patient = patient          # связываем объекты
    app.patient_id = patient.id    # явно заполняем внешний ключ
    app.note = note
    app.note_id = note.id  

    dto = AppointmentDTO.from_orm(app)
    assert dto.id == 5
    assert dto.patient_id == 1
    assert dto.patient_name == "Петров Иван"
    assert dto.note_id == 10
    assert dto.note_text == "Заметка"

def test_note_dto_from_orm():
    note = AppointmentNote(id=10, text="Текст")
    dto = AppointmentNoteDTO.from_orm(note)
    assert dto.id == 10
    assert dto.text == "Текст"

def test_photo_dto_from_orm():
    photo = Photo(id=20, appointment_id=5, file_path="path.jpg", description="desc")
    dto = PhotoDTO.from_orm(photo)
    assert dto.id == 20
    assert dto.appointment_id == 5
    assert dto.file_path == "path.jpg"
    assert dto.description == "desc"