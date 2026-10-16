# tests/test_repositories/test_repositories_review.py

"""
Проверка репозиториев (2026-10-16): REPO1–REPO3 из app/services/IMPLEMENTATION.md §3.2.
"""

from datetime import date

import pytest

from app.database.database_shema.clinic import Appointment, Patient
from app.repositories.repositories_all import AppointmentRepository, BaseRepository, PatientRepository


def _capture(repo):
    got = []
    handler = repo.logger.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    return got, handler


def test_repo1_unique_values_without_model_class(db_session):
    """REPO1: без model_class — понятный NotImplementedError, а не AttributeError."""
    class NoModel(BaseRepository):
        model_class = None

    with pytest.raises(NotImplementedError, match='model_class'):
        NoModel(db_session).get_unique_values('id')


def test_repo2_unknown_relation_warned(db_session, sample_patient):
    repo = PatientRepository(db_session)
    got, handler = _capture(repo)
    try:
        found = repo.get_with_relations(sample_patient.id, ['appointments', 'нет_такой_связи'])
    finally:
        repo.logger.remove_output(handler)
    assert found.id == sample_patient.id
    assert any(line.startswith('WARNING|') and 'нет_такой_связи' in line for line in got)


@pytest.mark.parametrize('repo_class', [AppointmentRepository])
def test_repo3_order_by_desc_string(db_session, sample_patient, repo_class):
    for day in (1, 3, 2):
        db_session.add(Appointment(patient_id=sample_patient.id, date=date(2026, 1, day)))
    db_session.commit()
    repo = repo_class(db_session)
    items = repo.get_page(0, 10, order_by=['-date'])
    assert [a.date.day for a in items] == [3, 2, 1]
    by_patient = repo.get_page_by_patient(sample_patient.id, 0, 2, order_by=['date'])
    assert [a.date.day for a in by_patient] == [1, 2]


def test_repo3_unknown_order_field_warned(db_session, sample_patient):
    repo = PatientRepository(db_session)
    got, handler = _capture(repo)
    try:
        assert repo.get_page(0, 10, order_by=['опечатка'])[0].id == sample_patient.id
    finally:
        repo.logger.remove_output(handler)
    assert any('опечатка' in line for line in got)


# ---------------------------------------------------------------------------
# Проход 2: характеризующие тесты непокрытых веток (параллельный путь репозиториев)
# ---------------------------------------------------------------------------

def test_all_with_relations_and_unique_values(db_session, sample_patient, sample_appointment):
    from sqlalchemy.orm import selectinload
    repo = AppointmentRepository(db_session)
    items = repo.get_all_with_relations([selectinload(Appointment.photos)])
    assert [a.id for a in items] == [sample_appointment.id]
    assert repo.get_unique_values('patient_id') == [sample_patient.id]
    assert repo.get_unique_values('нет_колонки') == []


def test_page_filters_relations_and_counts_by_patient(db_session, sample_patient):
    from sqlalchemy.orm import selectinload
    other = Patient(first_name='А', last_name='Б')
    db_session.add(other)
    db_session.commit()
    for day in (1, 2, 3):
        db_session.add(Appointment(patient_id=sample_patient.id, date=date(2026, 1, day)))
    db_session.add(Appointment(patient_id=other.id, date=date(2026, 1, 1)))
    db_session.commit()
    repo = AppointmentRepository(db_session)
    late = [{'column': 'date', 'operator': 'ge', 'value': date(2026, 1, 2)}]
    page = repo.get_page_by_patient(sample_patient.id, 0, 10, filters=late,
                                    relations=[selectinload(Appointment.photos)])
    assert sorted(a.date.day for a in page) == [2, 3]
    assert repo.count_by_patient(sample_patient.id) == 3
    assert repo.count_by_patient(sample_patient.id, filters=late) == 2
    assert len(repo.get_by_patient_with_relations(sample_patient.id, [selectinload(Appointment.photos)])) == 3
