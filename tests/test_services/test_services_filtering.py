import pytest
from datetime import date
from app.dto import PatientDTO
from app.services import PatientService
from app.exceptions import PatientNotFoundError

def test_patient_service_get_filtered_eq(patient_service, db_session, sample_patient):
    """
    Тест на равенство фильтрации.
    Проверяем, что запрос с фильтром равенства строится.
    """
    from app.database.database_shema.clinic import Patient
    # Добавим ещё одного
    p2 = Patient(first_name="Мария", last_name="Сидорова")
    db_session.add(p2)
    db_session.commit()

    filters = [{"column": "last_name", "operator": "eq", "value": "Петров"}]
    patients = patient_service.get_patients_filtered(filters)
    assert len(patients) == 1
    assert patients[0].id == sample_patient.id

def test_patient_service_get_filtered_like(patient_service, db_session):
    """
    Тест на фильтрацию LIKE.
    Проверяем, что запрос с фильтром LIKE строится.
    Создаём пациентов с разными фамилиями, а затем фильтруем по фамилии, содержащей "Иван".
    """
    from app.database.database_shema.clinic import Patient
    names = ["Иванов", "Иваненко", "Петров", "Сидоров"]
    for name in names:
        p = Patient(first_name="Test", last_name=name)
        db_session.add(p)
    db_session.commit()

    filters = [{"column": "last_name", "operator": "like", "value": "Иван"}]
    patients = patient_service.get_patients_filtered(filters)
    assert len(patients) == 2
    assert {p.last_name for p in patients} == {"Иванов", "Иваненко"}

def test_patient_service_get_filtered_fuzzy(patient_service, db_session):
    """
    Тест на фильтрацию fuzzy.
    Создаём пациентов с разными фамилиями, а затем фильтруем по фамилии, содержащей "Иванов".
    Проверяем, что запрос с фильтром fuzzy строится.
    """
    from app.database.database_shema.clinic import Patient
    names = ["Иванов", "Иванофф", "Петров"]
    for name in names:
        p = Patient(first_name="Test", last_name=name)
        db_session.add(p)
    db_session.commit()

    filters = [{"column": "last_name", "operator": "fuzzy", "value": "Иванов"}]
    patients = patient_service.get_patients_filtered(filters, fuzzy_threshold=70)
    assert len(patients) == 2  # Иванов и Иванофф (похожи)
    assert patients[0].last_name in ("Иванов", "Иванофф")