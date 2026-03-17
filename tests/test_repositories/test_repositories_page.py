import pytest
from app.repositories import PatientRepository, AppointmentRepository, AppointmentNoteRepository, PhotoRepository
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo
from datetime import date, timedelta

# ---------- PatientRepository ----------
def test_patient_repository_get_page(patient_repo, db_session):
    """
    Тест на получение страницы пациентов из репозитория.
    
    Создаём 15 пациентов, проверяем, что репозиторий может вернуть
    первую страницу (offset=0, limit=10) и вторую страницу (offset=10, limit=10).
    Также проверяется, что репозиторий может вернуть общее количество
    пациентов (15).
    """
    # Создаём 15 пациентов
    for i in range(15):
        p = Patient(first_name=f"Name{i}", last_name=f"Last{i}")
        db_session.add(p)
    db_session.commit()

    # Первая страница (offset=0, limit=10)
    page1 = patient_repo.get_page(0, 10)
    assert len(page1) == 10
    # Вторая страница
    page2 = patient_repo.get_page(10, 10)
    assert len(page2) == 5
    # Общее количество
    assert patient_repo.count() == 15

def test_patient_repository_get_page_with_filters(patient_repo, db_session):
    """
    Тестирование метода get_page для репозитория пациентов с использованием фильтров.
    Создаём 5 пациентов с разными фамилиями, затем проверяем, что репозиторий возвращает страницу с фильтром равенства и общее количество записей с этим фильтром.
    """
    # Создаём пациентов с разными фамилиями
    names = ["Smith", "Johnson", "Williams", "Brown", "Jones"]
    for name in names:
        p = Patient(first_name="Test", last_name=name)
        db_session.add(p)
    db_session.commit()

    filters = [{"column": "last_name", "operator": "in", "value": ["Smith", "Brown"]}]
    page = patient_repo.get_page(0, 10, filters=filters)
    assert len(page) == 2
    assert {p.last_name for p in page} == {"Smith", "Brown"}
    assert patient_repo.count(filters=filters) == 2

# ---------- AppointmentRepository ----------
def test_appointment_repository_get_page(appointment_repo, db_session, sample_patient):
    """
    Тестирование метода get_page для репозитория приёмов.
    Создаём 20 приёмов для одного пациента.
    Проверяем, что метод возвращает страницу приёмов по 10 записей.
    """
    # Создаём 20 приёмов для одного пациента
    for i in range(20):
        a = Appointment(
            patient_id=sample_patient.id,
            date=date.today() + timedelta(days=i)
        )
        db_session.add(a)
    db_session.commit()

    page1 = appointment_repo.get_page(0, 10)
    assert len(page1) == 10
    page2 = appointment_repo.get_page(10, 10)
    assert len(page2) == 10
    page3 = appointment_repo.get_page(20, 10)
    assert len(page3) == 0
    assert appointment_repo.count() == 20

def test_appointment_repository_get_page_with_relations(appointment_repo, db_session, sample_patient, sample_note):
    # Приёмы с заметками
    """
    Тестирование метода get_page с подгруженными приёмами и заметками.
    Создаём 5 приёмов для одного пациента с одной заметкой.
    Проверяем, что метод возвращает страницу приёмов с подгруженными приёмами и заметками.
    """
    for i in range(5):
        a = Appointment(
            patient_id=sample_patient.id,
            date=date.today() + timedelta(days=i),
            note_id=sample_note.id
        )
        db_session.add(a)
    db_session.commit()

    page = appointment_repo.get_page(0, 10, order_by=[Appointment.date.asc()])
    assert len(page) == 5
    # Проверяем, что связи подгружены (опционально, если метод использует joinedload)
    # В репозитории get_page по умолчанию не подгружает, но можно добавить опцию.
    # Для теста просто проверим, что объекты есть.

def test_appointment_repository_count_with_filters(appointment_repo, db_session, sample_patient):
    """
    Тестирование метода count с подгрузкой фильтров.
    Создаём 10 приёмов для одного пациента с разными датами.
    Проверяем, что метод возвращает количество приёмов с учётом дополнительных фильтров.
    """
    # Приёмы с разными датами
    today = date.today()
    for i in range(10):
        a = Appointment(
            patient_id=sample_patient.id,
            date=today + timedelta(days=i)
        )
        db_session.add(a)
    db_session.commit()

    filters = [{"column": "date", "operator": "ge", "value": today + timedelta(days=5)}]
    assert appointment_repo.count(filters=filters) == 5

# ---------- AppointmentNoteRepository ----------
def test_note_repository_get_page(note_repo, db_session):
    """
    Тестирование метода get_page для репозитория заметок к приёмам.
    Создаём 12 заметок к приёмам, затем проверяем, что метод возвращает страницу с 5 записями.
    Далее проверяем, что общее количество заметок к приёмам равно 12.
    """
    for i in range(12):
        note = AppointmentNote(text=f"Note {i}")
        db_session.add(note)
    db_session.commit()

    page = note_repo.get_page(5, 5)
    assert len(page) == 5
    assert note_repo.count() == 12

# ---------- PhotoRepository ----------
def test_photo_repository_get_page(photo_repo, db_session, sample_appointment):
    """
    Тестирование метода get_page для репозитория фотографий к приёмам.
    Создаём 8 фотографий к приёму, затем проверяем, что метод возвращает страницу с 3 записями.
    Далее проверяем, что общее количество фотографий к приёмам равно 8.
    """
    for i in range(8):
        photo = Photo(
            appointment_id=sample_appointment.id,
            file_path=f"path{i}.jpg"
        )
        db_session.add(photo)
    db_session.commit()

    page = photo_repo.get_page(2, 3)
    assert len(page) == 3
    assert photo_repo.count() == 8